from __future__ import annotations

import json
from collections import Counter

from audiobook import paths
from audiobook.text_blocks import extract_sections


def main() -> None:
    docx_path = paths.TEXT / "Ty_ne_polomann_v5.docx"
    blocks_dir = paths.TEXT / "blocks"
    blocks_dir.mkdir(parents=True, exist_ok=True)

    sections = extract_sections(docx_path)

    header = f"{'NN':>3} {'Section':<42} {'chars':>6} {'hdg':>4} {'para':>5} {'flow':>5} {'chain':>5} {'stack':>5} {'prse':>5}"
    print(header)
    print("-" * len(header))

    totals: Counter = Counter()

    for sec in sections:
        out_path = blocks_dir / f"{sec['nn']}_{sec['slug']}.blocks.json"
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(sec, f, ensure_ascii=False, indent=2)

        chars = sum(len(b['text']) for b in sec['blocks'])
        cnt: Counter = Counter(b['type'] for b in sec['blocks'])
        totals.update(cnt)
        totals['chars'] += chars

        print(
            f"{sec['nn']:>3} {sec['heading'][:42]:<42} {chars:>6} "
            f"{cnt['heading']:>4} {cnt['paragraph']:>5} {cnt['flow']:>5} "
            f"{cnt['chain']:>5} {cnt['stack']:>5} {cnt['prose_with_arrow']:>5}"
        )

    print("-" * len(header))
    print(
        f"{'TOT':>3} {'':42} {totals['chars']:>6} "
        f"{totals['heading']:>4} {totals['paragraph']:>5} {totals['flow']:>5} "
        f"{totals['chain']:>5} {totals['stack']:>5} {totals['prose_with_arrow']:>5}"
    )
    print(f"\nSchema blocks total: {totals['flow'] + totals['chain'] + totals['stack'] + totals['prose_with_arrow']}")


if __name__ == '__main__':
    main()
