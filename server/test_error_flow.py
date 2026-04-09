"""
Manual test script for error/back detection flow.

Safe by default:
- Only captures screen and checks templates.
- Does not tap/swipe/back unless --run-flow is provided.

Examples:
    python -m server.test_error_flow
    python -m server.test_error_flow --run-flow
    python server/test_error_flow.py --image ./sample.png
"""

import argparse
import importlib
import json
import logging
import os
import time
from typing import Optional

try:
    from .remote_adb import RemoteADB
    from .engine import BotEngine
    from .config import AGENT_URL, TEMPLATES_DIR
except ImportError:
    # Support: python server/test_error_flow.py
    from remote_adb import RemoteADB
    from engine import BotEngine
    from config import AGENT_URL, TEMPLATES_DIR

logger = logging.getLogger("test-error-flow")


def _load_screen_from_image(path: str):
    np = importlib.import_module("numpy")
    pil_image = importlib.import_module("PIL.Image")

    try:
        image = pil_image.open(path).convert("RGB")
    except Exception as exc:
        raise FileNotFoundError(f"Cannot read image: {path}") from exc

    if image is None:
        raise FileNotFoundError(f"Cannot read image: {path}")

    # Convert RGB -> BGR to match engine expectations.
    rgb = np.array(image)
    return rgb[:, :, ::-1]


def _capture_screen(engine: BotEngine, image_path: Optional[str]):
    if image_path:
        return _load_screen_from_image(image_path)
    return engine.load_screenshot(use_cache=False, force_refresh=True)


def _save_debug_overlay(screen_bgr, checks, output_path: str):
    np = importlib.import_module("numpy")
    pil_image = importlib.import_module("PIL.Image")
    image_draw = importlib.import_module("PIL.ImageDraw")
    image_font = importlib.import_module("PIL.ImageFont")

    rgb = np.array(screen_bgr)[:, :, ::-1]
    image = pil_image.fromarray(rgb.astype("uint8"))
    draw = image_draw.Draw(image)

    try:
        font = image_font.load_default()
    except Exception:
        font = None

    text_y = 10
    for item in checks:
        label = item["label"]
        threshold = float(item["threshold"])
        result = item["result"] or {}

        found = bool(result.get("found", False))
        conf = float(result.get("confidence", 0.0))
        template_name = result.get("template_name") or "-"

        color = item.get("color")
        if color is None:
            color = (46, 204, 113) if found else (231, 76, 60)

        point_color = item.get("point_color", (255, 0, 0))
        line = f"{label}: {'FOUND' if found else 'MISS'} conf={conf:.3f} thr={threshold:.2f} tpl={template_name}"
        draw.text((10, text_y), line, fill=color, font=font)
        text_y += 16

        bbox = result.get("bbox")
        if bbox:
            x, y, w, h = bbox
            draw.rectangle((x, y, x + w, y + h), outline=color, width=3 if found else 2)
            box_text = f"{label} {conf:.3f}"
            draw.text((x, max(0, y - 16)), box_text, fill=color, font=font)

        point = result.get("click_location")
        if point:
            px, py = point
            r = 6
            draw.ellipse((px - r, py - r, px + r, py + r), fill=point_color, outline=(255, 255, 255), width=1)
            draw.text((px + 8, max(0, py - 10)), f"{label}_click", fill=point_color, font=font)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    image.save(output_path)


def _build_debug_path(debug_dir: str, phase: str) -> str:
    ts = time.strftime("%Y%m%d_%H%M%S")
    return os.path.join(debug_dir, f"{phase}_{ts}.png")


def run_test(args) -> int:
    adb = RemoteADB(agent_url=args.agent_url)
    engine = BotEngine(adb=adb, templates_dir=args.templates_dir)

    health = adb.health_check()
    print("[health]", json.dumps(health, ensure_ascii=False))

    if not args.image and health.get("status") != "ok":
        print("[fatal] Agent is not reachable. Check AGENT_URL/local agent first.")
        return 2

    screen = _capture_screen(engine, args.image)

    task_info = engine.detect_task_title(screen_bgr=screen, threshold=args.task_threshold)
    time_info = engine.detect_time_cho(screen_bgr=screen, threshold=args.time_threshold)
    error_info = engine.detect_error_state(screen_bgr=screen, threshold=args.error_threshold)
    back_info = engine.find_back_area(screen_bgr=screen, threshold=args.back_threshold)

    has_time_wait = bool(time_info.get("found", False))
    has_error = bool(error_info.get("found", False))

    summary = {
        "task_found": bool(task_info.get("found", False)),
        "task_confidence": round(float(task_info.get("confidence", 0.0)), 4),
        "task_template": task_info.get("template_name"),
        "task_click": task_info.get("click_location"),
        "has_time_wait": has_time_wait,
        "time_confidence": round(float(time_info.get("confidence", 0.0)), 4),
        "time_template": time_info.get("template_name"),
        "has_error": has_error,
        "error_confidence": round(float(error_info.get("confidence", 0.0)), 4),
        "error_template": error_info.get("template_name"),
        "back_found": back_info.get("found", False),
        "back_template": back_info.get("template_name"),
        "back_confidence": round(float(back_info.get("confidence", 0.0)), 4),
        "back_rejected_reason": back_info.get("rejected_reason"),
    }
    print("[check]", json.dumps(summary, ensure_ascii=False))

    if back_info.get("rejected_reason") == "aspect_ratio":
        print(
            "[hint] back template đang giống thanh menu browser (quá dẹt). "
            "Hãy chụp lại template chỉ chứa icon back/close nhỏ hơn."
        )

    if not back_info.get("found", False):
        back_conf = float(back_info.get("confidence", 0.0))
        if back_conf >= max(0.0, args.back_threshold - 0.05):
            recommended = max(0.4, round(back_conf - 0.01, 2))
            print(
                f"[hint] back gần ngưỡng ({back_conf:.4f} < {args.back_threshold:.2f}). "
                f"Thử --back-threshold {recommended:.2f}"
            )

    if args.debug_draw:
        before_path = _build_debug_path(args.debug_dir, "error_flow_before")
        _save_debug_overlay(
            screen_bgr=screen,
            checks=[
                {
                    "label": "task_title",
                    "result": task_info,
                    "threshold": args.task_threshold,
                    "color": (255, 0, 255),
                    "point_color": (255, 0, 0),
                },
                {"label": "time_cho", "result": time_info, "threshold": args.time_threshold},
                {"label": "error", "result": error_info, "threshold": args.error_threshold},
                {"label": "back", "result": back_info, "threshold": args.back_threshold},
            ],
            output_path=before_path,
        )
        print("[debug]", before_path)

    # Safe mode: detection only.
    if not args.run_flow:
        print("[done] Detection-only mode complete (no device action executed).")
        return 0

    # Flow mode follows your automation logic branch.
    if has_time_wait:
        print("[skip] time_cho found; error branch is not needed.")
        return 0

    if not has_error:
        print("[skip] no error state found.")
        return 0

    if not back_info.get("found", False):
        print("[fail] error found but back template is not found.")
        return 1

    clicked = engine.click_back_template_center(screen_bgr=screen, threshold=args.back_threshold)
    if not clicked:
        print("[fail] could not click back area.")
        return 1

    print(f"[flow] clicked back area, waiting {args.wait_after_click}s...")
    time.sleep(args.wait_after_click)

    engine.back()
    print("[flow] adb back sent.")

    screen_after = _capture_screen(engine, args.image)
    confirm_info = engine.detect_btn_xn(screen_bgr=screen_after, threshold=args.confirm_threshold)
    has_confirm = bool(confirm_info.get("found", False))
    print("[result]", json.dumps({"confirm_found": has_confirm}, ensure_ascii=False))

    if args.debug_draw:
        after_path = _build_debug_path(args.debug_dir, "error_flow_after")
        _save_debug_overlay(
            screen_bgr=screen_after,
            checks=[
                {"label": "confirm", "result": confirm_info, "threshold": args.confirm_threshold},
            ],
            output_path=after_path,
        )
        print("[debug]", after_path)

    if has_confirm and args.auto_confirm:
        clicked_confirm = engine.click_confirm_button(screen_bgr=screen_after)
        print("[result]", json.dumps({"confirm_clicked": bool(clicked_confirm)}, ensure_ascii=False))

    return 0 if has_confirm else 1


def parse_args():
    parser = argparse.ArgumentParser(description="Test error/back detection flow")
    parser.add_argument("--agent-url", default=AGENT_URL, help="Local agent URL")
    parser.add_argument("--templates-dir", default=TEMPLATES_DIR, help="Templates directory")
    parser.add_argument("--image", default=None, help="Use local screenshot instead of remote capture")
    parser.add_argument("--run-flow", action="store_true", help="Execute click back + wait + adb back")
    parser.add_argument("--auto-confirm", action="store_true", help="Click confirm if found (only with --run-flow)")
    parser.add_argument("--debug-draw", action="store_true", help="Save debug overlay image")
    parser.add_argument("--debug-dir", default="debug", help="Directory for debug overlay images")

    parser.add_argument("--time-threshold", type=float, default=0.6)
    parser.add_argument("--error-threshold", type=float, default=0.55)
    parser.add_argument("--back-threshold", type=float, default=0.50)
    parser.add_argument("--confirm-threshold", type=float, default=0.7)
    parser.add_argument("--task-threshold", type=float, default=0.6)
    parser.add_argument("--wait-after-click", type=int, default=15)
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    args = parse_args()
    return run_test(args)


if __name__ == "__main__":
    raise SystemExit(main())
