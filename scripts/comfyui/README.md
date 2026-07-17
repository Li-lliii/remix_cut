# ComfyUI 手动联调脚本

这个目录放“直接调用 ComfyUI /prompt 的手动联调脚本”，不属于 pytest 自动化测试。

命名建议：

```text
test_{operation}_api_workflow.py
```

例如：

```text
test_replace_background_api_workflow.py
test_replace_clothes_api_workflow.py
test_replace_product_api_workflow.py
```

这些脚本用于验证：

- API workflow JSON 是否能提交到 ComfyUI
- 输入节点是否能正确替换
- 输出节点是否能保存结果
- ComfyUI 模型和节点依赖是否完整

平台正式接口仍然放在：

```text
metahuman_platform/platform_app/modules/ai_transforms/
```

自动化测试仍然放在：

```text
metahuman_platform/tests/
```
