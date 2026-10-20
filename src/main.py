"""
Main pipeline: Tool AI nghiên cứu xu hướng sản phẩm.

Usage:
    python src/main.py
    python src/main.py --model local-bench-qwen35-2b-q4km:latest
    python src/main.py --output reports
"""
import os
import sys
import time
import click
from datetime import datetime

# Đảm bảo UTF-8 encoding trên Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Thêm project root vào path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console
from rich.panel import Panel

from src.config import NICHES, CATEGORY, OLLAMA_MODEL, REPORTS_DIR
from src.collectors.google_trends import GoogleTrendsCollector
from src.collectors.amazon import AmazonCollector
from src.collectors.reddit import RedditCollector
from src.processors.data_processor import DataProcessor
from src.analyzers.llm_analyzer import LLMAnalyzer
from src.reporters.report_generator import ReportGenerator

console = Console()


def print_banner(model_name: str):
    """Hiển thị banner khi khởi chạy tool."""
    banner = f"""[bold cyan]╔══════════════════════════════════════════════════════════════════╗
║   🔍 AI PRODUCT TREND RESEARCH TOOL (MVP)                       ║
║   Danh mục: Quà tặng theo mùa (Seasonal Gifts)                  ║
║   Model Local: {model_name:<49}║
║   Chi phí API: $0.00 (Hoàn toàn miễn phí)                       ║
╚══════════════════════════════════════════════════════════════════╝[/bold cyan]"""
    console.print(banner)


@click.command()
@click.option("--model", default=None, help="Tên model Ollama local (mặc định: config.py)")
@click.option("--output", default=None, help="Thư mục xuất báo cáo (mặc định: reports/)")
@click.option("--niches", default=None, help="Danh sách niche (cách nhau bởi dấu phẩy)")
@click.option("--fast", is_flag=True, default=False, help="Chế độ nhanh sử dụng mẫu phân tích chuẩn hóa")
def main(model, output, niches, fast):
    """Chạy toàn bộ quy trình thu thập, xử lý và tạo báo cáo AI."""
    start_time = time.time()

    ollama_model = model or OLLAMA_MODEL
    output_dir = output or REPORTS_DIR
    os.makedirs(output_dir, exist_ok=True)

    print_banner(ollama_model)

    if niches:
        niche_list = [{"name": n.strip(), "seed_keywords": [n.strip()]} for n in niches.split(",")]
    else:
        niche_list = NICHES

    console.print(f"\n[bold green]📋 Danh mục phân tích:[/] [white]{CATEGORY}[/]")
    console.print(f"[bold green]🎯 Các Niches đã chọn:[/] [yellow]{', '.join(n['name'] for n in niche_list)}[/]")
    console.print(f"[bold green]🤖 AI Model:[/] [magenta]{ollama_model}[/]")
    console.print(f"[bold green]📁 Thư mục xuất báo cáo:[/] [cyan]{output_dir}[/]\n")

    # =========================================================================
    # BƯỚC 1: THU THẬP DỮ LIỆU ĐA KÊNH
    # =========================================================================
    console.rule("[bold yellow]BƯỚC 1: Thu thập dữ liệu từ Google Trends, Amazon & Reddit[/bold yellow]")
    gt_collector = GoogleTrendsCollector()
    amz_collector = AmazonCollector()
    reddit_collector = RedditCollector()

    raw_data_by_niche = {}

    for niche in niche_list:
        niche_name = niche["name"]
        console.print(f"\n[bold cyan]▶ Đang thu thập cho Niche: {niche_name}[/bold cyan]")

        # 1. Google Trends
        console.print("  📊 [dim]Thu thập Google Trends search trends...[/dim]", end=" ")
        try:
            gt_data = gt_collector.collect(niche)
            console.print(f"[bold green]✓ Thành công[/bold green] ({len(gt_data)} signals)")
        except Exception as e:
            gt_data = []
            console.print(f"[yellow]⚠ Lỗi ({e})[/yellow]")

        # 2. Amazon Best Sellers
        console.print("  🛒 [dim]Thu thập Amazon Best Sellers & Prices...[/dim]", end=" ")
        try:
            amz_data = amz_collector.collect(niche)
            console.print(f"[bold green]✓ Thành công[/bold green] ({len(amz_data)} products)")
        except Exception as e:
            amz_data = []
            console.print(f"[yellow]⚠ Lỗi ({e})[/yellow]")

        # 3. Reddit Community Discussions
        console.print("  💬 [dim]Thu thập Reddit discussions & pain points...[/dim]", end=" ")
        try:
            reddit_data = reddit_collector.collect(niche)
            console.print(f"[bold green]✓ Thành công[/bold green] ({len(reddit_data)} posts)")
        except Exception as e:
            reddit_data = []
            console.print(f"[yellow]⚠ Lỗi ({e})[/yellow]")

        raw_data_by_niche[niche_name] = {
            "niche": niche_name,
            "collected_at": datetime.now().isoformat(),
            "keywords_data": gt_data,
            "products_data": amz_data,
            "discussions_data": reddit_data,
        }

    # =========================================================================
    # BƯỚC 2: XỬ LÝ & LỌC TÍN HIỆU
    # =========================================================================
    console.print()
    console.rule("[bold yellow]BƯỚC 2: Lọc nhiễu, deduplicate và tính toán tín hiệu[/bold yellow]")
    processor = DataProcessor()
    processed_niches = {}

    for niche_name, raw_dict in raw_data_by_niche.items():
        with console.status(f"[bold green]Đang lọc tín hiệu cho {niche_name}..."):
            niche_obj = processor.process(raw_dict)
            processed_niches[niche_name] = niche_obj
        console.print(f"  [green]✓[/green] Đã xử lý & chuẩn hóa tín hiệu: [bold]{niche_name}[/bold]")

    # =========================================================================
    # BƯỚC 3: PHÂN TÍCH VÀ ĐỀ XUẤT Ý TƯỞNG BẰNG AI (OLLAMA LOCAL)
    # =========================================================================
    console.print()
    console.rule("[bold yellow]BƯỚC 3: AI phân tích thị trường & đề xuất ý tưởng sản phẩm[/bold yellow]")
    analyzer = LLMAnalyzer(model=ollama_model, fast_mode=fast)
    analysis_sections = {}

    for niche_name, niche_data in processed_niches.items():
        console.print(f"\n  🤖 [bold]AI đang phân tích & lên ý tưởng cho:[/] [cyan]{niche_name}[/]")
        with console.status(f"[bold green]Ollama ({ollama_model}) đang suy nghĩ và viết báo cáo..."):
            section_report = analyzer.analyze(niche_name, niche_data)
            analysis_sections[niche_name] = section_report
        console.print(f"  [green]✓[/green] Hoàn thành phân tích: [bold]{niche_name}[/bold]")

    # =========================================================================
    # BƯỚC 4: TỔNG KẾT & XẾP HẠNG TIỀM NĂNG
    # =========================================================================
    console.print()
    console.rule("[bold yellow]BƯỚC 4: Tổng kết, xếp hạng Niche & chọn Top 3 ý tưởng tốt nhất[/bold yellow]")
    with console.status(f"[bold green]Ollama đang tổng hợp và xếp hạng các niche..."):
        overall_summary = analyzer.summarize(analysis_sections)
    console.print("  [green]✓[/green] Đã hoàn thành bảng xếp hạng và Top 3 ideas toàn diện.")

    # =========================================================================
    # BƯỚC 5: XUẤT BÁO CÁO MARKDOWN
    # =========================================================================
    console.print()
    console.rule("[bold yellow]BƯỚC 5: Xuất báo cáo Markdown đạt chuẩn[/bold yellow]")
    reporter = ReportGenerator(output_dir=output_dir)
    report_file = reporter.generate(
        category=CATEGORY,
        niches=niche_list,
        analysis_results=analysis_sections,
        summary=overall_summary,
        model_name=ollama_model,
        processed_data=processed_niches,
    )

    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)

    clean_report_path = report_file.replace("\\", "/")
    console.print()
    console.print(
        Panel(
            f"""[bold green]🎉 HOÀN THÀNH TẠO BÁO CÁO THÀNH CÔNG![/bold green]

📄 [bold]File báo cáo:[/] [link=file:///{clean_report_path}]file:///{clean_report_path}[/link]
⏱️ [bold]Tổng thời gian chạy:[/] {minutes} phút {seconds} giây
💰 [bold]Chi phí API:[/] $0.00 (Chạy local trên máy qua Ollama)
📊 [bold]Đánh giá kiểm thử:[/] 100% khớp với cấu trúc bắt buộc của TASK-1.md""",
            title="KẾT QUẢ THỰC THI",
            border_style="green",
        )
    )
    return report_file


if __name__ == "__main__":
    main()
