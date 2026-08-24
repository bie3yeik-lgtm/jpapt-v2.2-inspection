#!/usr/bin/env python3
"""Normalize read-only Vast search output for CI artifacts."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

FIELDS = (
    "source_file", "offer_id", "machine_id", "gpu_name", "gpu_ram_gb", "num_gpus",
    "reliability", "verified", "rentable", "direct_port_count",
    "cuda_max_good", "dph_total", "dph_base", "dph_storage", "min_bid",
    "storage_cost", "disk_space_gb", "geolocation",
)


def _payload_offers(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        offers = payload.get("offers", payload.get("results", payload))
        if isinstance(offers, list):
            return [item for item in offers if isinstance(item, dict)]
        if isinstance(offers, dict):
            return [offers]
    raise ValueError("Vast raw response does not contain an offer list/object")


def _number(value: Any, divisor: float = 1.0) -> Any:
    if value is None or value == "":
        return None
    try:
        return round(float(value) / divisor, 4)
    except (TypeError, ValueError) as error:
        raise ValueError(f"non-numeric Vast field: {value!r}") from error


def normalize(profile: str, pricing_type: str, source: Path, offer: dict[str, Any]) -> dict[str, Any]:
    offer_id = offer.get("id", offer.get("ask_contract_id"))
    if offer_id is None:
        raise ValueError(f"{source}: offer has no id")
    return {
        "profile": profile, "pricing_type": pricing_type,
        "source_file": str(source).replace("\\", "/"), "offer_id": offer_id,
        "machine_id": offer.get("machine_id"), "gpu_name": offer.get("gpu_name"),
        "gpu_ram_gb": _number(offer.get("gpu_ram"), 1024), "num_gpus": offer.get("num_gpus"),
        "reliability": offer.get("reliability"), "verified": offer.get("verified"),
        "rentable": offer.get("rentable"), "direct_port_count": offer.get("direct_port_count"),
        "cuda_max_good": offer.get("cuda_max_good"), "dph_total": offer.get("dph_total"),
        "dph_base": offer.get("dph_base"), "dph_storage": offer.get("dph_storage"),
        "min_bid": offer.get("min_bid"), "storage_cost": offer.get("storage_cost"),
        "disk_space_gb": offer.get("disk_space"), "geolocation": offer.get("geolocation"),
    }


def render_markdown(inventory: dict[str, Any]) -> str:
    lines = [
        "# Vast rentable offer inventory", "",
        f"- profile: `{inventory['profile']}`",
        f"- pricing_type: `{inventory['pricing_type']}`",
        f"- offer_count: `{len(inventory['offers'])}`", "",
        "| Offer ID | GPU | VRAM GB | GPUs | Reliability | Verified | Rentable | Direct ports | $/h total | $/h base | $/h storage | Min bid | Location |",
        "|---:|---|---:|---:|---:|:---:|:---:|---:|---:|---:|---:|---:|---|",
    ]
    for offer in inventory["offers"]:
        lines.append(
            "| {offer_id} | {gpu_name} | {gpu_ram_gb} | {num_gpus} | {reliability} | "
            "{verified} | {rentable} | {direct_port_count} | {dph_total} | {dph_base} | "
            "{dph_storage} | {min_bid} | {geolocation} |".format(**offer)
        )
    if not inventory["offers"]:
        lines.append("| — | No matching rentable offer | — | — | — | — | — | — | — | — | — | — | — |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--pricing-type", required=True)
    parser.add_argument("--limit", type=int, required=True)
    args = parser.parse_args()

    offers: list[dict[str, Any]] = []
    for source in sorted(args.input_dir.glob("*.json")):
        if source.name == "inventory.json":
            continue
        payload = json.loads(source.read_text(encoding="utf-8"))
        profile = source.name.split("-", 1)[0]
        for raw_offer in _payload_offers(payload):
            offers.append(normalize(profile, args.pricing_type, source, raw_offer))
    offers.sort(key=lambda item: (item["dph_total"] is None, item["dph_total"] or float("inf"), str(item["offer_id"])))
    offers = offers[: args.limit * (2 if args.profile == "all" else 1)]

    inventory = {"schema_version": 1, "profile": args.profile, "pricing_type": args.pricing_type,
                 "offer_count": len(offers), "offers": offers}
    for path in (args.output_json, args.output_csv, args.output_markdown):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with args.output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("profile", "pricing_type", *FIELDS))
        writer.writeheader()
        writer.writerows(offers)
    args.output_markdown.write_text(render_markdown(inventory), encoding="utf-8")


if __name__ == "__main__":
    main()
