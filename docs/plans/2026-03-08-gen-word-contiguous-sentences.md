# Gen Word Contiguous Sentences Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将步骤2中的参考文本抽取逻辑改为随机选取一段连续句子，并让 `num_segments` 表示连续句子数量。

**Architecture:** 保持 `generate_speech_text()` 的公开接口基本不变，仅调整 `utils/gen_word.py` 内部抽取逻辑。新增一个最小单测覆盖抽取行为，验证返回内容来自原文中同一连续窗口而非离散拼接。

**Tech Stack:** Python, `unittest`, `requests`

---

### Task 1: 为连续句窗口抽取补测试

**Files:**
- Create: `D:\code\project\2026\codex\remix_cut\tests\test_gen_word.py`
- Modify: `D:\code\project\2026\codex\remix_cut\utils\gen_word.py`

**Step 1: Write the failing test**

```python
def test_select_random_segments_returns_one_contiguous_window():
    text = "第一句。第二句。第三句。第四句。第五句。第六句。"
    result = _select_random_segments(text, num_segments=3, seed=0)
    assert result == ["第四句。第五句。第六句。"]
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest discover -s tests -p "test_gen_word.py" -v`
Expected: FAIL because current logic returns sampled merged candidates instead of one continuous sentence window.

**Step 3: Write minimal implementation**

```python
sentences = _split_into_sentences(text)
start = rng.randint(0, len(sentences) - window_size)
return ["".join(sentences[start:start + window_size])]
```

**Step 4: Run test to verify it passes**

Run: `python -m unittest discover -s tests -p "test_gen_word.py" -v`
Expected: PASS

### Task 2: 同步更新参数语义与日志

**Files:**
- Modify: `D:\code\project\2026\codex\remix_cut\utils\gen_word.py`
- Modify: `D:\code\project\2026\codex\remix_cut\remix_cut.py`

**Step 1: Update docstrings and CLI help**

将 `num_segments` 的说明改为“连续句子数”，将 `min_seg_chars` / `max_seg_chars` 标记为兼容保留但不参与抽取。

**Step 2: Update runtime logs**

打印连续窗口的句数与预览，避免继续使用“抽取多个片段”的表述。

**Step 3: Run the targeted test again**

Run: `python -m unittest discover -s tests -p "test_gen_word.py" -v`
Expected: PASS

### Task 3: 轻量回归检查

**Files:**
- Modify: `D:\code\project\2026\codex\remix_cut\utils\gen_word.py`
- Modify: `D:\code\project\2026\codex\remix_cut\remix_cut.py`

**Step 1: Verify no other callsites rely on old meaning**

Run: `rg -n "num_segments|min_seg_chars|max_seg_chars|segments" D:\code\project\2026\codex\remix_cut`

**Step 2: Run a syntax check**

Run: `python -m py_compile D:\code\project\2026\codex\remix_cut\utils\gen_word.py D:\code\project\2026\codex\remix_cut\remix_cut.py D:\code\project\2026\codex\remix_cut\tests\test_gen_word.py`
Expected: no output
