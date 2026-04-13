"""Template patch manager.

Responsibilities:
  - Clone note types into app-managed variants (e.g. "Basic (AI Rewriter)")
  - Add app-owned fields (AIRewriteData, AIRewriteMeta, AIValidationData)
  - Inject randomization JavaScript into card templates
  - Support idempotent re-patching
  - Store original templates in DB for rollback
  - Produce a human-readable diff preview before any changes
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.anki_client import AnkiClient, AnkiConnectError
from backend.config import settings
from backend.note_type_registry import NoteKind, NoteTypeClassification, SupportLevel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Anki card template JS inserted at the end of the front template.
# Reads AIRewriteData and AIRewriteMeta to show the selected variant.
# ---------------------------------------------------------------------------

_FRONT_JS_MARKER = "<!-- AI_REWRITER_FRONT_v1 -->"

_FRONT_JS_TEMPLATE = """\
{marker}
<div id="ai-rewrite-data-raw" style="display:none">{{{{AIRewriteData}}}}</div>
<div id="ai-rewrite-meta-raw" style="display:none">{{{{AIRewriteMeta}}}}</div>
<div id="ai-rewrite-prompt" style="display:none"></div>
<script>
(function() {{
  var dataRaw = document.getElementById('ai-rewrite-data-raw');
  var metaRaw = document.getElementById('ai-rewrite-meta-raw');
  var promptDiv = document.getElementById('ai-rewrite-prompt');
  if (!dataRaw || !metaRaw || !promptDiv) return;

  var dataText = dataRaw.textContent.trim();
  var metaText = metaRaw.textContent.trim();
  if (!dataText || dataText === '{{AIRewriteData}}') return;

  try {{
    var data = JSON.parse(dataText);
    var meta = JSON.parse(metaText || '{{}}');
    var templateName = '{template_name}';

    var tplInfo = data.templates && data.templates[templateName];
    if (!tplInfo) return;

    var promptField = tplInfo.prompt_field;
    var fieldData = data.fields && data.fields[promptField];
    if (!fieldData || !fieldData.variants || fieldData.variants.length === 0) return;

    var selectedIdx = (meta.selected_variant_idx !== undefined)
      ? meta.selected_variant_idx
      : 0;
    var variant = fieldData.variants[selectedIdx % fieldData.variants.length];
    if (!variant || !variant.text) return;

    promptDiv.style.display = '';
    promptDiv.innerHTML = variant.text;

    // Hide the original field div and show our variant
    var origField = document.getElementById('original-prompt-field');
    if (origField) origField.style.display = 'none';

    // Store selected variant for back side via sessionStorage (best effort)
    try {{ sessionStorage.setItem('ai_rv_' + templateName, String(selectedIdx)); }} catch(e) {{}}
  }} catch(e) {{ /* silently ignore */ }}
}})();
</script>"""

_BACK_JS_MARKER = "<!-- AI_REWRITER_BACK_v1 -->"

_BACK_JS_TEMPLATE = """\
{marker}
<div id="ai-rewrite-data-raw-back" style="display:none">{{{{AIRewriteData}}}}</div>
<div id="ai-rewrite-meta-raw-back" style="display:none">{{{{AIRewriteMeta}}}}</div>
<div id="ai-rewrite-prompt-back" style="display:none"></div>
<script>
(function() {{
  var dataRaw = document.getElementById('ai-rewrite-data-raw-back');
  var metaRaw = document.getElementById('ai-rewrite-meta-raw-back');
  var promptDiv = document.getElementById('ai-rewrite-prompt-back');
  if (!dataRaw || !metaRaw || !promptDiv) return;

  var dataText = dataRaw.textContent.trim();
  if (!dataText || dataText === '{{AIRewriteData}}') return;

  try {{
    var data = JSON.parse(dataText);
    var meta = JSON.parse((metaRaw.textContent || '').trim() || '{{}}');
    var templateName = '{template_name}';

    var tplInfo = data.templates && data.templates[templateName];
    if (!tplInfo) return;

    var promptField = tplInfo.prompt_field;
    var fieldData = data.fields && data.fields[promptField];
    if (!fieldData || !fieldData.variants || fieldData.variants.length === 0) return;

    // Recover selection from sessionStorage first, then fall back to meta
    var selectedIdx = (meta.selected_variant_idx !== undefined)
      ? meta.selected_variant_idx
      : 0;
    try {{
      var stored = sessionStorage.getItem('ai_rv_' + templateName);
      if (stored !== null) selectedIdx = parseInt(stored, 10);
    }} catch(e) {{}}

    var variant = fieldData.variants[selectedIdx % fieldData.variants.length];
    if (!variant || !variant.text) return;

    promptDiv.style.display = '';
    promptDiv.innerHTML = variant.text;

    var origField = document.getElementById('original-prompt-field-back');
    if (origField) origField.style.display = 'none';
  }} catch(e) {{ /* silently ignore */ }}
}})();
</script>"""


@dataclass
class TemplateDiff:
    template_name: str
    original_front: str
    patched_front: str
    original_back: str
    patched_back: str


@dataclass
class PatchPlan:
    original_model_name: str
    patched_model_name: str
    fields_to_add: list[str]
    template_diffs: list[TemplateDiff]
    is_clone: bool
    already_patched: bool = False
    warnings: list[str] = field(default_factory=list)


class TemplatePatchManager:
    def __init__(self, anki: AnkiClient) -> None:
        self.anki = anki

    # ------------------------------------------------------------------
    # Public: build a plan (no mutations yet)
    # ------------------------------------------------------------------

    async def build_patch_plan(
        self,
        model_name: str,
        classification: NoteTypeClassification,
    ) -> PatchPlan:
        """
        Compute what changes would be needed to patch this note type.

        Does NOT write anything to Anki. Returns a PatchPlan that can be
        shown to the user for approval.
        """
        patched_name = self._patched_model_name(model_name)
        existing_models = await self.anki.model_names()

        # If the cloned model already exists, inspect it
        if patched_name in existing_models:
            field_names = await self.anki.model_field_names(patched_name)
            already_patched = self._are_app_fields_present(field_names)
            if already_patched:
                return PatchPlan(
                    original_model_name=model_name,
                    patched_model_name=patched_name,
                    fields_to_add=[],
                    template_diffs=[],
                    is_clone=True,
                    already_patched=True,
                    warnings=["This note type has already been patched."],
                )

        # Get original model info
        field_names = await self.anki.model_field_names(model_name)
        templates_html = await self.anki.model_templates(model_name)
        fields_on_templates = await self.anki.model_fields_on_templates(model_name)

        fields_to_add = [
            f
            for f in [
                settings.ai_rewrite_data_field,
                settings.ai_rewrite_meta_field,
                settings.ai_validation_data_field,
            ]
            if f not in field_names
        ]

        template_diffs: list[TemplateDiff] = []
        for tpl_name, tpl_html in templates_html.items():
            orig_front = tpl_html.get("Front", "")
            orig_back = tpl_html.get("Back", "")

            front_fields = fields_on_templates.get(tpl_name, [[], []])[0]
            prompt_field = front_fields[0] if front_fields else "Front"

            patched_front = self._patch_front_template(orig_front, tpl_name, prompt_field)
            patched_back = self._patch_back_template(orig_back, tpl_name)

            template_diffs.append(
                TemplateDiff(
                    template_name=tpl_name,
                    original_front=orig_front,
                    patched_front=patched_front,
                    original_back=orig_back,
                    patched_back=patched_back,
                )
            )

        warnings: list[str] = []
        if classification.support_level == SupportLevel.CAUTION:
            warnings.append(
                "This note type is in CAUTION mode. Review the diff carefully before applying."
            )

        return PatchPlan(
            original_model_name=model_name,
            patched_model_name=patched_name,
            fields_to_add=fields_to_add,
            template_diffs=template_diffs,
            is_clone=True,
            already_patched=False,
            warnings=warnings + classification.notes,
        )

    # ------------------------------------------------------------------
    # Public: apply a patch plan (after user approval)
    # ------------------------------------------------------------------

    async def apply_patch(self, plan: PatchPlan) -> dict[str, Any]:
        """
        Execute the patch plan:
          1. Clone the note type if it doesn't exist yet
          2. Add app-owned fields
          3. Patch card templates

        Returns a dict with the original template HTML for rollback storage.
        """
        if plan.already_patched:
            return {"status": "already_patched", "patched_model_name": plan.patched_model_name}

        original_model = plan.original_model_name
        patched_model = plan.patched_model_name
        existing_models = await self.anki.model_names()

        # Fetch original data for rollback record
        orig_field_names = await self.anki.model_field_names(original_model)
        orig_templates = await self.anki.model_templates(original_model)
        orig_css_data = await self.anki.model_styling(original_model)
        orig_css = orig_css_data.get("css", "") if isinstance(orig_css_data, dict) else ""

        rollback_data = {
            "original_model_name": original_model,
            "field_names": orig_field_names,
            "templates": orig_templates,
            "css": orig_css,
        }

        if patched_model not in existing_models:
            # Clone: create new model with all fields + app fields + patched templates
            all_fields = orig_field_names + [
                f for f in plan.fields_to_add if f not in orig_field_names
            ]

            card_templates = []
            for diff in plan.template_diffs:
                card_templates.append({
                    "Name": diff.template_name,
                    "Front": diff.patched_front,
                    "Back": diff.patched_back,
                })

            await self.anki.create_model(
                model_name=patched_model,
                fields=all_fields,
                css=orig_css,
                card_templates=card_templates,
            )
            logger.info("Created cloned model: %s", patched_model)
        else:
            # Already exists but missing app fields or templates need updating
            existing_fields = await self.anki.model_field_names(patched_model)
            for f in plan.fields_to_add:
                if f not in existing_fields:
                    await self.anki.model_field_add(patched_model, f)
                    logger.info("Added field %s to %s", f, patched_model)

            # Update templates
            templates_update: dict[str, dict[str, str]] = {}
            for diff in plan.template_diffs:
                templates_update[diff.template_name] = {
                    "Front": diff.patched_front,
                    "Back": diff.patched_back,
                }
            await self.anki.update_model_templates(patched_model, templates_update)
            logger.info("Updated templates for %s", patched_model)

        return {
            "status": "applied",
            "patched_model_name": patched_model,
            "rollback_data": rollback_data,
        }

    # ------------------------------------------------------------------
    # Rollback
    # ------------------------------------------------------------------

    async def rollback_patch(self, patch_record: Any) -> None:
        """
        Given a TemplatePatch DB record, attempt to restore original templates.

        Note: removing fields from Anki note types is destructive. The rollback
        only restores templates; field removal must be done manually.
        """
        patched_model = patch_record.patched_model_name
        existing_models = await self.anki.model_names()
        if patched_model not in existing_models:
            raise AnkiConnectError(f"Model {patched_model!r} not found in Anki.")

        orig_templates = json.loads(patch_record.original_template_html)
        templates_update: dict[str, dict[str, str]] = {}
        for tpl_name, tpl_data in orig_templates.items():
            templates_update[tpl_name] = {
                "Front": tpl_data.get("Front", ""),
                "Back": tpl_data.get("Back", ""),
            }
        await self.anki.update_model_templates(patched_model, templates_update)
        logger.info("Rolled back templates for %s", patched_model)

    # ------------------------------------------------------------------
    # App-field status check
    # ------------------------------------------------------------------

    def is_model_app_managed(self, field_names: list[str]) -> bool:
        return self._are_app_fields_present(field_names)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _patched_model_name(self, model_name: str) -> str:
        suffix = settings.app_model_suffix
        if model_name.endswith(suffix):
            return model_name
        return f"{model_name}{suffix}"

    def _are_app_fields_present(self, field_names: list[str]) -> bool:
        return settings.ai_rewrite_data_field in field_names

    def _patch_front_template(
        self, original: str, template_name: str, prompt_field: str
    ) -> str:
        if _FRONT_JS_MARKER in original:
            return original  # idempotent

        js_block = _FRONT_JS_TEMPLATE.format(
            marker=_FRONT_JS_MARKER,
            template_name=template_name,
        )
        # Wrap original prompt field in a div so JS can hide it
        orig_field_tag = f"{{{{{prompt_field}}}}}"
        wrapped = f'<div id="original-prompt-field">{orig_field_tag}</div>'
        patched = original.replace(orig_field_tag, wrapped, 1)
        return patched + "\n" + js_block

    def _patch_back_template(self, original: str, template_name: str) -> str:
        if _BACK_JS_MARKER in original:
            return original  # idempotent

        js_block = _BACK_JS_TEMPLATE.format(
            marker=_BACK_JS_MARKER,
            template_name=template_name,
        )
        return original + "\n" + js_block
