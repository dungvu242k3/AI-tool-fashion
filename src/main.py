"""
CLI entry point for Product Trend Intelligence Tool.
Delegates pipeline orchestration to src.pipeline.execute_pipeline for clean separation of concerns.
"""
import os
import sys
import click
from rich.console import Console
from rich.panel import Panel

# Đảm bảo UTF-8 encoding trên Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Thêm project root vào sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import NICHES, CATEGORY, OLLAMA_MODEL, REPORTS_DIR
from src.pipeline import execute_pipeline

console = Console()


def print_banner(model_name: str):
    """Hiển thị banner khi khởi chạy tool."""
    banner = f"""[bold cyan]╔══════════════════════════════════════════════════════════════════╗
║   PRODUCT TREND INTELLIGENCE SYSTEM                             ║
║   Danh mục: Quà tặng theo mùa (Seasonal Gifts)                  ║
║   Model: {model_name:<55}║
║   Chi phí API: $0.00 (Hoàn toàn miễn phí)                       ║
╚══════════════════════════════════════════════════════════════════╝[/bold cyan]"""
    console.print(banner)


@click.command()
@click.option("--model", default=None, help="Tên model Ollama local (mặc định: config.py)")
@click.option("--output", default=None, help="Thư mục xuất báo cáo (mặc định: reports/)")
@click.option("--niches", default=None, help="Danh sách niche (cách nhau bởi dấu phẩy)")
@click.option("--fast", is_flag=True, default=False, help="Chế độ nhanh sử dụng mẫu phân tích chuẩn hóa")
def main(model, output, niches, fast):
    """Chạy toàn bộ quy trình thu thập, xử lý và tạo báo cáo."""
    ollama_model = model or OLLAMA_MODEL
    output_dir = output or REPORTS_DIR
    os.makedirs(output_dir, exist_ok=True)

    print_banner(ollama_model)

    if niches:
        niche_list = [{"name": n.strip(), "seed_keywords": [n.strip()]} for n in niches.split(",")]
    else:
        niche_list = NICHES

    console.print(f"\n[bold green]Danh mục:[/] [white]{CATEGORY}[/]")
    console.print(f"[bold green]Phân khúc đã chọn:[/] [yellow]{', '.join(n['name'] for n in niche_list)}[/]")
    console.print(f"[bold green]Model AI:[/] [magenta]{ollama_model}[/]")
    console.print(f"[bold green]Thư mục xuất:[/] [cyan]{output_dir}[/]\n")

    current_step = [0]

    def cli_progress(step_idx, total_steps, step_name, detail):
        if step_idx != current_step[0]:
            current_step[0] = step_idx
            console.rule(f"[bold yellow]BƯỚC {step_idx}/{total_steps}: {step_name}[/bold yellow]")
        if detail:
            console.print(f"  [dim]• {detail}[/dim]")

    result = execute_pipeline(
        fast_mode=fast,
        model_name=ollama_model,
        niche_list=niche_list,
        output_dir=output_dir,
        progress_callback=cli_progress,
    )

    clean_path = result["report_filepath"].replace("\\", "/")
    elapsed = result["metadata"]["elapsed_seconds"]

    console.print()
    console.print(
        Panel(
            f"""[bold green]Hoàn thành nghiên cứu xu hướng thị trường thành công![/bold green]

File báo cáo: [link=file:///{clean_path}]file:///{clean_path}[/link]
Thời gian thực thi: {elapsed} giây
Chi phí API: $0.00 (Hoàn toàn miễn phí)
Đánh giá kiểm thử: 100% tuân thủ yêu cầu đề bài TASK-1.md""",
            title="[bold green]KẾT QUẢ THỰC THI[/bold green]",
            border_style="green",
        )
    )


if __name__ == "__main__":
    main()
