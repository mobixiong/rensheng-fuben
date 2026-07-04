from app.subtitle_renderer import _matching_subtitle_chunks, _subtitle_events


def test_matching_subtitle_chunks_are_used_when_semantics_match():
    voiceover = "你每天六点起床，打开手机接第一单。雨水打在头盔上，你还是按下开始。"
    chunks = ["你每天六点起床，打开手机接第一单。", "雨水打在头盔上，你还是按下开始。"]

    assert _matching_subtitle_chunks(voiceover, chunks) == chunks
    events = _subtitle_events([{"start": 0, "end": 4, "voiceover": voiceover, "subtitle_chunks": chunks}])
    assert [event["text"] for event in events] == chunks


def test_mismatched_subtitle_chunks_fall_back_to_voiceover_split():
    voiceover = "你把手机扣在方向盘上。那一刻你没有说话。"
    stale_chunks = ["这是一段旧字幕，和当前口播完全不一致。"]

    assert _matching_subtitle_chunks(voiceover, stale_chunks) == []
    events = _subtitle_events([{"start": 0, "end": 3, "voiceover": voiceover, "subtitle_chunks": stale_chunks}])

    assert "旧字幕" not in "".join(event["text"] for event in events)
    assert "".join(event["text"] for event in events) == voiceover


def test_empty_subtitle_chunks_do_not_block_subtitle_generation():
    voiceover = "你以为这次终于选对了。可账本摊开以后，数字还是不对。"

    events = _subtitle_events([{"start": 1, "end": 5, "voiceover": voiceover, "subtitle_chunks": []}])

    assert events
    assert "".join(event["text"] for event in events) == voiceover
