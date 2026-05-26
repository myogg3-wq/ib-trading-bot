from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
import re
from typing import Dict, List

from fastapi.testclient import TestClient

from app.main import create_app


STATIC_DIR = Path(__file__).resolve().parent / "static"


@dataclass
class AuditCheck:
    key: str
    title: str
    score: int
    max_score: int
    verdict: str
    evidence: str
    next_action: str


@dataclass
class AuditReport:
    overall_score: int
    overall_max: int
    summary: str
    checks: List[AuditCheck]
    next_iteration_queue: List[str]
    artifacts: Dict[str, str]


def _read_static_file(name: str) -> str:
    return (STATIC_DIR / name).read_text(encoding="utf-8")


def _extract_localized_value(source: str, key: str, *, lang: str) -> str:
    if lang == "ko":
        pattern = rf'{key}:\s*"([^"]+)",'
        blocks = source.split("ko:") if "ko:" in source else [source]
        target = blocks[-1]
    else:
        pattern = rf"{key}:\s*\"([^\"]+)\","
        target = source
    match = re.search(pattern, target)
    return match.group(1) if match else ""


def _score_band(value: int, *, good: int, warn: int) -> int:
    if value <= good:
        return 10
    if value <= warn:
        return 7
    return 4


def _build_checks(html: str, css: str, js: str, i18n: str) -> List[AuditCheck]:
    checks: List[AuditCheck] = []

    topbar_interactives = len(re.findall(r'class="[^"]*(?:subnav-chip|language-picker|topbar-cta|live-pill)[^"]*"', html))
    search_hidden = "body[data-active-tab=\"research\"] .topbar-search" in css and "display: none" in css
    topbar_score = min(10, _score_band(topbar_interactives, good=4, warn=6) + (1 if search_hidden else -1))
    checks.append(
        AuditCheck(
            key="topbar_noise",
            title="상단 노이즈",
            score=max(1, topbar_score),
            max_score=10,
            verdict="good" if topbar_score >= 8 else "warn",
            evidence=f"상단 인터랙션 요소 {topbar_interactives}개, 리서치 탭 검색 숨김={search_hidden}",
            next_action="브랜드, 언어, 탭 외 보조 요소는 리서치 탭에서 계속 숨긴다.",
        )
    )

    title_ko = _extract_localized_value(i18n, "researchStageTitle", lang="ko")
    desc_ko = _extract_localized_value(i18n, "researchStageDescription", lang="ko")
    copy_score = min(10, _score_band(len(title_ko), good=14, warn=22) + _score_band(len(desc_ko), good=28, warn=42) - 10)
    checks.append(
        AuditCheck(
            key="hero_copy",
            title="메인 카피 압축도",
            score=max(1, copy_score),
            max_score=10,
            verdict="good" if copy_score >= 8 else "warn",
            evidence=f"한글 제목 {len(title_ko)}자, 설명 {len(desc_ko)}자",
            next_action="제목은 1행 또는 짧은 2행 안에, 설명은 1문장으로 유지한다.",
        )
    )

    results_unified = all(
        token in js
        for token in [
            "research-results-shell",
            "research-query-shell",
            "research-answer-shell",
            "premium-map-shell",
        ]
    )
    grid_hidden = "el.aiRoundtableGrid.hidden = true" in js
    results_score = 10 if results_unified and grid_hidden else 5
    checks.append(
        AuditCheck(
            key="results_unification",
            title="결과 화면 일체감",
            score=results_score,
            max_score=10,
            verdict="good" if results_score >= 8 else "warn",
            evidence=f"단일 리서치 셸={results_unified}, 별도 그리드 숨김={grid_hidden}",
            next_action="질문, 무료 답변, 유료 목차를 한 캔버스 안에서만 유지한다.",
        )
    )

    section_count = len(re.findall(r'id:\s*"[a-z\-]+"', js[js.find("const sections = ["): js.find("return {", js.find("const sections = ["))]))
    paid_count = len(re.findall(r"credits:\s*\d+", js))
    collapsed_sections = "const initiallyVisible = sections.slice(0, 4);" in js and "premium-more-shell" in js
    monetization_score = 10 if collapsed_sections else 10 if section_count <= 7 else 7 if section_count <= 9 else 4
    checks.append(
        AuditCheck(
            key="premium_density",
            title="유료 섹션 밀도",
            score=monetization_score,
            max_score=10,
            verdict="good" if monetization_score >= 8 else "warn",
            evidence=f"총 섹션 {section_count}개, 크레딧 섹션 {paid_count}개, 기본 노출 제한={collapsed_sections}",
            next_action="첫 화면에 기본 노출되는 유료 항목 수를 제한하고, 나머지는 접어둔다.",
        )
    )

    editorial_canvas = "linear-gradient(180deg, rgba(255, 251, 244" in css
    search_shell = ".ai-roundtable-form-hero" in css and "border-radius: 999px" in css
    theme_score = 10 if editorial_canvas and search_shell else 6
    checks.append(
        AuditCheck(
            key="theme_blend",
            title="검색형 + 리서치형 조합",
            score=theme_score,
            max_score=10,
            verdict="good" if theme_score >= 8 else "warn",
            evidence=f"밝은 캔버스={editorial_canvas}, 검색형 입력바={search_shell}",
            next_action="다크 쉘 안에 밝은 리서치 캔버스를 유지해 정체성을 고정한다.",
        )
    )

    return checks


def build_design_audit() -> AuditReport:
    html = _read_static_file("platform.html")
    css = _read_static_file("platform.css")
    js = _read_static_file("platform.js")
    i18n = _read_static_file("platform-i18n.js")

    client = TestClient(create_app(skip_startup=True))
    response = client.get("/platform")
    served_html = response.text if response.status_code == 200 else html

    checks = _build_checks(served_html, css, js, i18n)
    overall_max = sum(check.max_score for check in checks)
    overall_score = sum(check.score for check in checks)

    weak_checks = [check for check in checks if check.score < 8]
    if overall_score >= int(overall_max * 0.85):
        summary = "현재 디자인은 반복 개선 루프를 돌릴 기반은 갖췄지만, 여전히 약한 구간을 계속 눌러야 합니다."
    else:
        summary = "현재 디자인은 반복 개선 시스템이 꼭 필요한 상태이며, 특히 약한 구간부터 순서대로 줄여야 합니다."

    next_iteration_queue = [check.next_action for check in weak_checks] or [
        "현재 점수가 유지되면 타이포와 간격 통일 같은 마감 개선으로 넘어간다."
    ]

    return AuditReport(
        overall_score=overall_score,
        overall_max=overall_max,
        summary=summary,
        checks=checks,
        next_iteration_queue=next_iteration_queue,
        artifacts={},
    )


def render_markdown(report: AuditReport) -> str:
    lines = [
        "# Design Recursive Improvement Report",
        "",
        f"- Overall score: {report.overall_score}/{report.overall_max}",
        f"- Summary: {report.summary}",
        "",
        "## Checks",
        "",
    ]

    for check in report.checks:
        lines.extend(
            [
                f"### {check.title}",
                f"- Score: {check.score}/{check.max_score}",
                f"- Verdict: {check.verdict}",
                f"- Evidence: {check.evidence}",
                f"- Next action: {check.next_action}",
                "",
            ]
        )

    lines.extend(["## Next Iteration Queue", ""])
    for item in report.next_iteration_queue:
        lines.append(f"- {item}")

    if report.artifacts:
        lines.extend(["", "## Artifacts", ""])
        for key, value in report.artifacts.items():
            lines.append(f"- {key}: {value}")

    lines.append("")
    return "\n".join(lines)


def render_json(report: AuditReport) -> str:
    payload = {
        "overall_score": report.overall_score,
        "overall_max": report.overall_max,
        "summary": report.summary,
        "checks": [asdict(check) for check in report.checks],
        "next_iteration_queue": report.next_iteration_queue,
        "artifacts": report.artifacts,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
