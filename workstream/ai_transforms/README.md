# AI Transform Workflows

Place ComfyUI API-format workflow JSON files here.

The first supported API workflow path is:

```text
workstream/ai_transforms/replace_background_api.json
```

`replace_background` requires `params.node_overrides` when submitting a task.
Each key is a dotted node path in the workflow, and each value may use these
placeholders:

```text
{video}
{background_image}
{filename_prefix}
{seed}
```

Example:

```json
{
  "node_overrides": {
    "47.inputs.video": "{video}",
    "12.inputs.image": "{background_image}",
    "46.inputs.filename_prefix": "{filename_prefix}",
    "53.inputs.seed": "{seed}"
  }
}
```
