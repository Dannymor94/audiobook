from __future__ import annotations

import argparse
import os
import sys

from . import paths


def config_path():
    """config.yaml, or AUDIOBOOK_CONFIG (relative to the project root) for an
    A/B trial with a temporary copy — never for the book render."""
    import os
    from pathlib import Path
    env = os.environ.get("AUDIOBOOK_CONFIG")
    if not env:
        return paths.ROOT / "config.yaml"
    p = Path(env)
    return p if p.is_absolute() else paths.ROOT / p


def load_config() -> dict:
    import yaml
    with open(config_path(), encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_parser() -> argparse.ArgumentParser:
    """The whole CLI parser; jobqueue uses it to validate `queue add` args."""
    p = argparse.ArgumentParser(prog="audiobook")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("doctor", help="проверка окружения")
    d.add_argument("--no-models", action="store_true", help="не проверять веса (CI)")
    bn = sub.add_parser("bench", help="RTF: N воркеров × T потоков (подбор render.cpu_threads)")
    bn.add_argument("--workers", type=int, default=1, help="параллельных воркеров (default 1)")
    bn.add_argument("--threads", type=int, default=None,
                    help="потоков torch на воркер (default: render.cpu_threads или cpu/воркеры)")
    fx = sub.add_parser("fix", help="разметка на слух → план → redo в очередь → страница выбора")
    fxs = fx.add_subparsers(dest="fix_cmd", required=True)
    fp = fxs.add_parser("plan", help="план из labels_*.json и/или журнала → out/fix/plan.json")
    fp.add_argument("files", nargs="*", help="labels_*.json (без файлов — журнал text/labels.yaml)")
    fp.add_argument("--journal", action="store_true", help="добавить журнал text/labels.yaml к файлам")
    fp.add_argument("--since", default=None, help="записи журнала не раньше ГГГГ-ММ-ДД")
    fq = fxs.add_parser("queue", help="redo каждого чанка плана в очередь (всё или ничего)")
    fq.add_argument("--candidates", type=int, default=3, help="новых кандидатов на чанк (default 3)")
    fxs.add_parser("review", help="одна страница с кандидатами чанков плана → out/fix/review.html")
    sy = sub.add_parser("sync", help="карта текст↔время главы для читалки → section.sync.json")
    sy.add_argument("--section", default=None)
    sy.add_argument("--all", action="store_true", help="все собранные секции")
    im = sub.add_parser("impact", help="сколько отрендеренного перерендерит текущая правка настроек")
    im.add_argument("--section", default=None)
    im.add_argument("--verbose", action="store_true", help="показать затронутые чанки")
    vp = sub.add_parser("voice-plan", help="приватный план произношения и интонаций без синтеза")
    vp.add_argument("--section", required=True)
    vp.add_argument("--rules", help="локальный JSON: точная фраза → кандидат произношения")
    vp.add_argument("--sentence-ms", type=int)
    vp.add_argument("--paragraph-ms", type=int)
    vp.add_argument("--heading-ms", type=int, help="пауза после заголовка уровня 1")
    vp.add_argument("--chapter-title-carrier", action="store_true",
                    help="пробный контекст номера главы для названия")
    vp.add_argument("--tag", default="plan")
    dc = sub.add_parser("decisions", help="страница решений на слух (build) и применение decisions.json (apply)")
    dcs = dc.add_subparsers(dest="decisions_cmd", required=True)
    dcs.add_parser("build", help="out/decisions/index.html + media/ (копии звука)")
    da = dcs.add_parser("apply", help="применить decisions.json к config.yaml и text/pronounce.yaml")
    da.add_argument("file")
    da.add_argument("--dry-run", action="store_true", help="только показать изменения")
    sub.add_parser("notify-test", help="Telegram: отправить «проверка связи» (AUDIOBOOK_TG_TOKEN/CHAT из .env)")
    pg = sub.add_parser("passage", help="A/B отрывка подряд (стыки, контекст, паузы) → out/passage/<tag>/")
    pg.add_argument("--section", required=True)
    pg.add_argument("--start", type=int, default=1, help="номер первого чанка (n, с 1)")
    pg.add_argument("--count", type=int, default=15, help="сколько чанков подряд (default 15)")
    pg.add_argument("--tag", required=True, help="имя варианта (латиница), например base / ctx")
    ex = sub.add_parser("export", help="готовая книга из section.mp3 → out/export/ (mp3-набор или m4b)")
    ex.add_argument("--format", choices=("mp3", "m4b"), default="mp3")
    ex.add_argument("--allow-missing", action="store_true",
                    help="пропустить неготовые главы (книга будет неполной)")
    es = sub.add_parser("export-sample", help="отрывок ≤ 5 мин для магазина → out/export/sample.mp3")
    es.add_argument("--section", required=True)
    es.add_argument("--start", type=float, default=0.0, help="начало, с (default 0)")
    es.add_argument("--length", type=float, default=300.0, help="длина, с (≤ 300, default 300)")
    sub.add_parser("credits", help="вступление/концовка из config credits → out/credits/ (модель)")
    lp = sub.add_parser("listen-plan", help="что послушать человеку: подозрения + начала глав + выборка → out/listen/")
    lp.add_argument("--section", nargs="+", action="extend", default=None, help="только эти секции")
    lp.add_argument("--intro-s", type=float, default=30, help="сколько секунд начала каждой главы (default 30)")
    lp.add_argument("--random", type=int, default=20, help="случайных фраз по всем секциям (default 20)")
    lp.add_argument("--tag", default=None, help="папка out/listen/<tag>/ (по главе — имя секции)")
    lp.add_argument("--notify", action="store_true", help="отправить план в Telegram (если настроен)")
    sub.add_parser("pace", help="темп чтения по главам: отклонения от медианы книги")
    sub.add_parser("status", help="статус книги: что отрендерено, что ждёт человека, сколько осталось")
    sub.add_parser("pick-ref", help="синтез тестового отрывка для всех кандидатов ref/candidates/")
    sub.add_parser("calibrate", help="гриды скорости и паузы → out/ref_test2, speed_test, pause_test")
    ck = sub.add_parser("chunk", help="чанкинг разделов → out/sections/NN/manifest.jsonl")
    ck.add_argument("--section", type=str, default=None,
                    help="только эта секция (без флага — вся книга)")
    sub.add_parser("headings", help="рендер 483 заголовков → out/headings_check_v2/")
    rd = sub.add_parser("redo", help="рендер N кандидатов для чанка → out/redo/<sec>/<id>/")
    rd.add_argument("section", help="имя секции (например 01_vvedenie)")
    rd.add_argument("chunk_id", help="id чанка (например 0003)")
    rd.add_argument("--candidates", type=int, default=3, help="число кандидатов (default 3)")
    rc = sub.add_parser("ref-compare",
                        help="кандидаты ref/candidates/*.wav на одном тексте → out/ref_compare/")
    rc.add_argument("--section", type=str, default=None)
    rc.add_argument("--first", type=int, default=None, help="первые N чанков секции")
    rc.add_argument("--transcribe", action="store_true",
                    help="только черновики текста (whisper) для кандидатов без .txt")
    rs = sub.add_parser("ref-scout",
                        help="поиск кандидатов референса в длинной живой записи → ref/candidates/")
    rs.add_argument("src", help="путь к записи (m4a/wav/mp3)")
    rs.add_argument("--k", type=int, default=6, help="сколько кандидатов (default 6)")
    rs.add_argument("--tol", type=float, default=0.10,
                    help="допуск темпа к текущему референсу (default 0.10 = ±10%%)")
    pt = sub.add_parser("pron-test",
                        help="один чанк с разными написаниями слова → out/pron_test/")
    pt.add_argument("--section", required=True)
    pt.add_argument("--word", required=True, help="слово как в тексте (регистр важен)")
    pt.add_argument("--try", dest="variants", nargs="+", required=True,
                    help="написания для модели; '-' = без замены")
    pt.add_argument("--chunk", default=None, help="id чанка (иначе первый с этим словом)")
    pt.add_argument("--chunks", type=int, default=1,
                    help="сколько первых чанков с этим словом взять (default 1)")
    pt.add_argument("--seeds", type=int, default=2,
                    help="дублей на вариант (разные seed; default 2)")
    pb = sub.add_parser("probe",
                        help="подборка чанков с ловушками ударения по всей книге → out/probe/")
    pb.add_argument("--max", type=int, default=60, help="максимум чанков (default 60)")
    pb.add_argument("--dry-run", action="store_true", help="только показать выбор, без синтеза")
    su = sub.add_parser("suspects",
                        help="места для прослушки (после qc + assemble) → <stem>.suspects.tsv")
    su.add_argument("--section", required=True)
    su.add_argument("--first", type=int, default=None)
    jo = sub.add_parser("joins",
                        help="метрики стыков чанков (F0, темп, громкость) → <stem>.joins.tsv")
    jo.add_argument("--section", required=True)
    jo.add_argument("--first", type=int, default=None)
    ph = sub.add_parser("phoneme-check",
                        help="ЭКСПЕРИМЕНТ: ударение и лишний [j] по фонемам в wav из папки")
    ph.add_argument("--dir", default=None, help="папка с *.wav (например out/pron_test/…)")
    ph.add_argument("--expect", nargs="+", default=None,
                    help="слова с ударной гласной заглавной: запИть тебЯ дышИ")
    ph.add_argument("--auto", action="store_true",
                    help="автоматические кандидаты из stress_watch.yaml + pronounce.yaml")
    ph.add_argument("--section", default=None,
                    help="секция для --auto (NN_slug, обязательно с --auto)")
    ph.add_argument("--first", type=int, default=None,
                    help="только первые N чанков (с --auto)")
    sub.add_parser("lint-text",
                   help="проверка text/*.norm.txt: пропущенная ё, опечатки, что читать по буквам → out/lint/text_lint.md")
    gd = sub.add_parser("golden",
                        help="постоянный набор трудных чанков: init | render | compare")
    gsub = gd.add_subparsers(dest="golden_cmd", required=True)
    gi = gsub.add_parser("init", help="создать text/golden_set.yaml")
    gi.add_argument("--force", action="store_true", help="перезаписать существующий файл")
    gi.add_argument("--max", type=int, default=40, help="максимум чанков от probe (default 40)")
    gr = gsub.add_parser("render", help="рендер набора → out/golden/<tag>/")
    gr.add_argument("--tag", required=True, help="имя прогона (например baseline)")
    gr.add_argument("--workers", type=int, default=1,
                    help="игнорируется: golden всегда рендерит одним воркером")
    gc = gsub.add_parser("compare", help="пары A/B → out/golden/compare_A_B/")
    gc.add_argument("tag_a")
    gc.add_argument("tag_b")
    pf = sub.add_parser("preflight", help="проверка машины перед работой: ресурсы, процессы, git, doctor")
    pf.add_argument("--min-free-gb", type=float, default=16.0, help="минимум available RAM (default 16)")
    pf.add_argument("--max-load", type=float, default=4.0, help="максимум load за 1 мин (default 4)")
    pf.add_argument("--no-models", action="store_true", help="doctor без проверки весов")
    qp = sub.add_parser("queue", help="очередь тяжёлых задач (замок out/queue/heavy.lock)")
    qs = qp.add_subparsers(dest="queue_cmd", required=True)
    qa = qs.add_parser("add", help="queue add -- <аргументы run.sh>; synth/chunk только с --section")
    qa.add_argument("job_args", nargs="*")
    qs.add_parser("list", help="задачи в очереди и выполненные")
    qr = qs.add_parser("run", help="воркер: выполнять pending по одной, пока очередь не опустеет")
    qr.add_argument("--watch", type=float, default=None, metavar="SECONDS",
                    help="не выходить на пустой очереди: проверять её каждые SECONDS с (служба)")
    qr.add_argument("--requeue-interrupted", action="store_true",
                    help="задачу, прерванную перезагрузкой/падением, вернуть в очередь (до 3 раз)")
    ld = sub.add_parser("loudness",
                        help="громкость глав: LUFS / true peak / LRA → out/loudness/report.tsv")
    ld.add_argument("--section", nargs="+", action="extend", default=None,
                    help="только эти секции (без флага — все out/sections/*/section.mp3)")
    ld.add_argument("--ref-dir", nargs="+", action="extend", default=[],
                    help="папка или файл с эталонными записями (только для сравнения)")
    sub.add_parser("pron-audit",
                   help="аудит text/pronounce.yaml: срабатывания по книге, мёртвые записи → out/pron_audit.tsv")
    qsec = qs.add_parser("section", help="вся секция в очередь: chunk→synth→qc→assemble→master→suspects")
    qsec.add_argument("section")
    qsec.add_argument("--workers", type=int, default=2, help="воркеров synth (default 2)")
    qsec.add_argument("--first", type=int, default=None, help="только первые N чанков (превью)")
    qrd = qs.add_parser("redo", help="redo нескольких чанков секции в очередь")
    qrd.add_argument("section")
    qrd.add_argument("chunk_ids", nargs="+", help="id чанков, например 0012 0031")
    qrd.add_argument("--candidates", type=int, default=3)
    rv = sub.add_parser("review",
                        help="страница прослушки с кнопками хорошо/плохо/? → <папка>/review.html")
    rv.add_argument("--dir", required=True, help="папка с *.wav (pron_test, redo, probe, golden…)")
    rv.add_argument("--title", default=None, help="название (default: имя папки)")
    rv.add_argument("--meta", default=None, help="tsv с подписями (колонки file или n/chunk + любые)")
    lb = sub.add_parser("labels", help="журнал решений на слух text/labels.yaml")
    lbs = lb.add_subparsers(dest="labels_cmd", required=True)
    li = lbs.add_parser("import", help="дописать в журнал labels_*.json со страницы прослушки")
    li.add_argument("file", help="labels_<title>.json")
    li.add_argument("--section", default=None, help="секция для всех записей файла")
    ls = lbs.add_parser("show", help="показать журнал")
    ls.add_argument("--section", default=None)
    ac = sub.add_parser("accept", help="установить кандидат и заблокировать чанк")
    ac.add_argument("section")
    ac.add_argument("chunk_id")
    ac.add_argument("variant", type=int, help="номер варианта (1-based)")
    ao = sub.add_parser("accept-original", help="принять существующий WAV после прослушивания")
    ao.add_argument("section")
    ao.add_argument("chunk_id")
    ao.add_argument("--hash", required=True)
    ao.add_argument("--wav-sha256", required=True)
    ao.add_argument("--actual-seed", required=True, type=int)

    for name in ("synth", "qc", "assemble", "master"):
        s = sub.add_parser(name)
        s.add_argument("--chapter", type=int, default=None)
        s.add_argument("--section", type=str, default=None,
                       help="имя секции out/sections/<section> (обязательно для рендера)")
        if name == "synth":
            s.add_argument("--workers", type=int, default=1,
                           help="параллельных воркеров синтеза (Ryzen 0.6B: 4, 1.7B: 2)")
        if name == "qc":
            s.add_argument("--check-only", nargs="+", metavar="CHUNK",
                           help="измерить выбранные WAV без синтеза и ресинхронизации")
        if name in ("synth", "assemble", "master"):
            s.add_argument("--first", type=int, default=None,
                           help="только первые N чанков секции (превью → preview_firstN)")
    return p


def main(argv: list[str] | None = None) -> int:
    paths.apply_env_defaults()
    a = build_parser().parse_args(argv)
    if a.cmd in _MAIN_CONFIG_ONLY and os.environ.get("AUDIOBOOK_CONFIG"):
        print(f"{a.cmd}: AUDIOBOOK_CONFIG задан — эта команда пишет в кеш и манифесты "
              "книги и работает только с config.yaml", file=sys.stderr)
        return 2
    heavy = a.cmd in _HEAVY or (a.cmd == "probe" and not a.dry_run) or (
        a.cmd == "golden" and getattr(a, "golden_cmd", "") == "render")
    if heavy:
        from .jobqueue import heavy_command_lock
        with heavy_command_lock(a.cmd):
            return _dispatch(a)
    return _dispatch(a)


# Commands that write the book's cache/manifests: never with a trial config.
_MAIN_CONFIG_ONLY = {"chunk", "synth", "qc", "accept", "accept-original", "redo", "assemble", "master",
                     "headings", "credits", "export"}
# Commands that load a model or rewrite a section: one at a time (heavy.lock).
_HEAVY = {"chunk", "synth", "qc", "accept", "accept-original", "redo", "pron-test", "ref-compare",
          "ref-scout", "phoneme-check", "headings", "bench", "pick-ref", "calibrate",
          "credits", "passage"}


def _dispatch(a) -> int:

    if a.cmd == "doctor":
        from .doctor import run as doctor
        return 0 if doctor(a.no_models, load_config()) else 1
    if a.cmd == "fix":
        from . import fix
        if a.fix_cmd == "plan":
            return fix.cmd_plan(a.files, a.journal, a.since)
        if a.fix_cmd == "queue":
            return fix.cmd_queue(a.candidates)
        return fix.cmd_review()
    if a.cmd == "sync":
        from .sync import run as sync
        return sync(load_config(), a.section, a.all)
    if a.cmd == "impact":
        from .impact import run as impact
        return impact(load_config(), a.section, a.verbose)
    if a.cmd == "voice-plan":
        from .voice_plan import run as voice_plan
        return voice_plan(load_config(), a.section, a.rules, a.sentence_ms,
                          a.paragraph_ms, a.heading_ms, a.tag, a.chapter_title_carrier)
    if a.cmd == "decisions":
        from . import decisions
        if a.decisions_cmd == "build":
            return decisions.run_build(load_config())
        return decisions.run_apply(load_config(), a.file, a.dry_run)
    if a.cmd == "notify-test":
        from .notify import cli_test
        return cli_test()
    if a.cmd == "passage":
        from .passage import run as passage
        return passage(load_config(), a.section, a.start, a.count, a.tag)
    if a.cmd == "export":
        from .export import run_export
        return run_export(load_config(), a.format, a.allow_missing)
    if a.cmd == "export-sample":
        from .export import run_sample
        return run_sample(load_config(), a.section, a.start, a.length)
    if a.cmd == "credits":
        from .export import run_credits
        return run_credits(load_config())
    if a.cmd == "listen-plan":
        from .listen import run as listen_plan
        return listen_plan(load_config(), a.section, a.intro_s, a.random, a.tag, a.notify)
    if a.cmd == "pace":
        from .pace import run as pace
        return pace(load_config())
    if a.cmd == "status":
        from .status import run as status
        return status(load_config())
    if a.cmd == "bench":
        from .bench import run as bench
        cfg = load_config()
        return bench(cfg, a.workers, a.threads or (cfg.get("render") or {}).get("cpu_threads"))
    if a.cmd == "pick-ref":
        from .pick_ref import run as pick_ref
        return pick_ref(load_config())
    if a.cmd == "chunk":
        from .chunker import run as chunk
        return chunk(load_config(), a.section)
    if a.cmd == "headings":
        from .headings import run as headings
        return headings(load_config())
    if a.cmd == "calibrate":
        from .calibrate import run as calibrate
        return calibrate(load_config())
    if a.cmd == "redo":
        from .redo import run_redo
        return run_redo(load_config(), a.section, a.chunk_id, a.candidates)
    if a.cmd == "ref-compare":
        from .ref_compare import run as ref_compare
        return ref_compare(load_config(), a.section, a.first, a.transcribe)
    if a.cmd == "ref-scout":
        from .ref_scout import run as ref_scout
        return ref_scout(load_config(), a.src, a.k, a.tol)
    if a.cmd == "pron-test":
        from .pron_test import run as pron_test
        return pron_test(load_config(), a.section, a.word, a.variants, a.chunk, a.seeds,
                         a.chunks)
    if a.cmd == "probe":
        from .probe import run as probe
        return probe(load_config(), a.max, a.dry_run)
    if a.cmd == "suspects":
        from .suspects import run as suspects
        return suspects(load_config(), a.section, a.first)
    if a.cmd == "joins":
        from .joins import run as joins
        return joins(load_config(), a.section, a.first)
    if a.cmd == "phoneme-check":
        from . import phoneme_check as _pc
        if a.auto:
            if not a.section:
                raise SystemExit("phoneme-check --auto требует --section")
            return _pc.run_auto(load_config(), a.section, a.first)
        if not a.dir or not a.expect:
            raise SystemExit("phoneme-check: нужны --dir и --expect (или --auto --section)")
        return _pc.run(load_config(), a.dir, a.expect)
    if a.cmd == "lint-text":
        from .text_lint import run as lint_text
        return lint_text(load_config())
    if a.cmd == "golden":
        from . import golden
        if a.golden_cmd == "init":
            return golden.run_init(load_config(), a.force, a.max)
        if a.golden_cmd == "render":
            return golden.run_render(load_config(), a.tag, a.workers)
        return golden.run_compare(load_config(), a.tag_a, a.tag_b)
    if a.cmd == "preflight":
        from .preflight import run as preflight
        return 0 if preflight(load_config(), a.max_load, a.min_free_gb, a.no_models) else 1
    if a.cmd == "queue":
        from .jobqueue import cli as queue_cli, cli_shortcut
        if a.queue_cmd in ("section", "redo"):
            return cli_shortcut(a)
        return queue_cli(a.queue_cmd, getattr(a, "job_args", []),
                         watch=getattr(a, "watch", None),
                         requeue_interrupted=getattr(a, "requeue_interrupted", False))
    if a.cmd == "loudness":
        from .loudness import report as loudness
        return loudness(load_config(), a.section, a.ref_dir)
    if a.cmd == "pron-audit":
        from .pron_audit import run as pron_audit
        return pron_audit(load_config())
    if a.cmd == "review":
        from .review import run as review
        return review(a.dir, a.title, a.meta)
    if a.cmd == "labels":
        from . import labels
        if a.labels_cmd == "import":
            return labels.run_import(a.file, a.section)
        return labels.run_show(a.section)
    if a.cmd == "accept-original":
        from .redo import run_accept_original
        return run_accept_original(load_config(), a.section, a.chunk_id,
                                   a.hash, a.wav_sha256, a.actual_seed)
    if a.cmd == "accept":
        from .redo import run_accept
        return run_accept(load_config(), a.section, a.chunk_id, a.variant)
    if a.cmd == "synth":
        from .synth import run as synth
        return synth(load_config(), a.section, a.workers, a.first)
    if a.cmd == "qc":
        from . import qc
        if a.check_only is not None:
            return qc.check_selected(load_config(), a.section, a.check_only)
        return qc.run(load_config(), a.section)
    if a.cmd == "assemble":
        from .assemble import run as assemble
        return assemble(load_config(), a.section, a.first)
    if a.cmd == "master":
        from .master import run as master
        return master(load_config(), a.section, a.first)
    print(f"{a.cmd}: не реализовано в каркасе", file=sys.stderr)
    return 2


if __name__ == "__main__":
    import multiprocessing as mp
    mp.set_start_method("spawn", force=True)   # как на Windows, всегда
    sys.exit(main())
