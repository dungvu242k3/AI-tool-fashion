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
║   Danh mục: {CATEGORY:<49}║
║   Model: {model_name:<55}║
║   Chi phí API trực tiếp: $0.00                                 ║
╚══════════════════════════════════════════════════════════════════╝[/bold cyan]"""
    console.print(banner)


@click.command()
@click.option("--model", default=None, help="Tên model Ollama local (mặc định: config.py)")
@click.option("--output", default=None, help="Thư mục xuất báo cáo (mặc định: reports/)")
@click.option("--niches", default=None, help="Danh sách niche (cách nhau bởi dấu phẩy)")
@click.option("--fast", is_flag=True, default=False, help="Thu thập live và tổng hợp số liệu, không gọi LLM")
def main(model, output, niches, fast):
    """Chạy toàn bộ quy trình thu thập, xử lý và tạo báo cáo."""
    ollama_model = model or OLLAMA_MODEL
    output_dir = output or REPORTS_DIR
    os.makedirs(output_dir, exist_ok=True)

    print_banner(ollama_model if not fast else "Không dùng LLM")

    if niches:
        names = [name.strip() for name in niches.split(",")]
        if not all(names):
            raise click.BadParameter("Tên niche không được rỗng.", param_hint="--niches")
        configured = {niche["name"].casefold(): niche for niche in NICHES}
        niche_list = [configured.get(name.casefold(), {"name": name, "seed_keywords": [name]}) for name in names]
    else:
        niche_list = NICHES

    console.print(f"\n[bold green]Danh mục:[/] [white]{CATEGORY}[/]")
    console.print(f"[bold green]Phân khúc đã chọn:[/] [yellow]{', '.join(n['name'] for n in niche_list)}[/]")
    console.print(f"[bold green]Chế độ:[/] {'Tổng hợp dữ liệu, không gọi LLM' if fast else ollama_model}")
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

    status_text = "Hoàn tất thu thập" if result["success"] else "Báo cáo chưa đầy đủ"
    color = "green" if result["success"] else "yellow"
    console.print()
    console.print(
        Panel(
            f"""[bold {color}]{status_text}[/bold {color}]

File báo cáo: [link=file:///{clean_path}]file:///{clean_path}[/link]
Thời gian thực thi: {elapsed} giây
Trạng thái: {result['status']}
Chất lượng dữ liệu: {result['metadata']['data_quality']}
Chi phí API: $0.00 (không gồm chi phí máy và điện)""",
            title="KẾT QUẢ THỰC THI",
            border_style=color,
        )
    )
    for warning in result["metadata"]["warnings"]:
        console.print(f"[yellow]Lưu ý:[/] {warning}")
    if not result["success"]:
        raise click.exceptions.Exit(1)


if __name__ == "__main__":
    main()
