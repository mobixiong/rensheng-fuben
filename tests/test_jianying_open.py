from __future__ import annotations

import json

from app import jianying_open


def test_open_draft_syncs_to_jianying_root(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    source = workspace / "projects" / "p1" / "jianying_drafts" / "测试草稿"
    source.mkdir(parents=True)
    (source / "draft_content.json").write_text("{}", encoding="utf-8")
    (source / "draft_meta_info.json").write_text(
        json.dumps({"draft_id": "draft-test-id", "draft_name": "", "draft_fold_path": "", "draft_root_path": ""}, ensure_ascii=False),
        encoding="utf-8",
    )
    (source / "export_manifest.json").write_text(
        json.dumps({"draft_name": "测试草稿", "duration_sec": 1.25}, ensure_ascii=False),
        encoding="utf-8",
    )

    local_appdata = tmp_path / "local"
    appdata = tmp_path / "roaming"
    project_config = local_appdata / "JianyingPro" / "User Data" / "Projects" / "com.lveditor.draft"
    user_draft_root = tmp_path / "JianyingPro Drafts"
    user_draft_root.mkdir(parents=True)
    project_config.mkdir(parents=True)
    (project_config / "root_meta_info.json").write_text(
        json.dumps({
            "all_draft_store": [],
            "draft_ids": 0,
            "root_path": str(user_draft_root),
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    shortcut = appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "剪映专业版" / "剪映专业版.lnk"
    shortcut.parent.mkdir(parents=True)
    shortcut.write_text("", encoding="utf-8")

    launched: list[str] = []
    monkeypatch.setattr(jianying_open, "WORKSPACE", workspace)
    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setattr(jianying_open.os, "startfile", lambda path: launched.append(str(path)), raising=False)

    result = jianying_open.open_draft_in_jianying(str(source))

    target = user_draft_root / "测试草稿"
    assert result["ok"] is True
    assert target.exists()
    assert (target / "draft_content.json").exists()
    assert launched == [str(shortcut)]

    root_meta = json.loads((project_config / "root_meta_info.json").read_text(encoding="utf-8"))
    assert root_meta["all_draft_store"][0]["draft_name"] == "测试草稿"
    assert root_meta["all_draft_store"][0]["tm_duration"] == 1_250_000
    assert (project_config / "root_meta_info.json.bak_rensheng").exists()
