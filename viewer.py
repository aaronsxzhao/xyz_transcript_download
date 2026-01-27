"""
Beautiful summary viewer with multiple output formats.
"""
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table
from rich.tree import Tree
from rich.text import Text
from rich import box

from config import DATA_DIR


@dataclass
class KeyPoint:
    topic: str
    summary: str
    original_quote: str
    timestamp: str = ""


@dataclass
class Summary:
    episode_id: str
    title: str
    overview: str
    key_points: list
    topics: list
    takeaways: list


def load_summary(episode_id: str) -> Optional[Summary]:
    """Load a summary from file."""
    summary_path = DATA_DIR / "summaries" / f"{episode_id}.json"
    if not summary_path.exists():
        return None
    
    with open(summary_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    key_points = [
        KeyPoint(
            topic=kp.get("topic", ""),
            summary=kp.get("summary", ""),
            original_quote=kp.get("original_quote", ""),
            timestamp=kp.get("timestamp", ""),
        )
        for kp in data.get("key_points", [])
    ]
    
    return Summary(
        episode_id=data.get("episode_id", episode_id),
        title=data.get("title", ""),
        overview=data.get("overview", ""),
        key_points=key_points,
        topics=data.get("topics", []),
        takeaways=data.get("takeaways", []),
    )


def display_summary_rich(summary: Summary, console: Console):
    """Display summary with beautiful Rich formatting."""
    
    # Title
    console.print()
    console.print(Panel(
        Text(summary.title, style="bold white", justify="center"),
        title="📻 Podcast Summary",
        title_align="left",
        border_style="blue",
        padding=(1, 2),
    ))
    
    # Overview
    console.print()
    console.print(Panel(
        summary.overview,
        title="📝 Overview",
        title_align="left",
        border_style="green",
        padding=(1, 2),
    ))
    
    # Topics as a horizontal list
    console.print()
    topics_text = Text()
    for i, topic in enumerate(summary.topics):
        if i > 0:
            topics_text.append("  •  ", style="dim")
        topics_text.append(topic, style="cyan")
    console.print(Panel(
        topics_text,
        title="🏷️ Topics",
        title_align="left",
        border_style="cyan",
        padding=(0, 2),
    ))
    
    # Key Points grouped by topic
    console.print()
    console.print("[bold magenta]💡 Key Points[/bold magenta]")
    console.print()
    
    # Group key points by topic
    topics_map = {}
    for kp in summary.key_points:
        if kp.topic not in topics_map:
            topics_map[kp.topic] = []
        topics_map[kp.topic].append(kp)
    
    for topic, points in topics_map.items():
        # Topic header
        console.print(f"  [bold cyan]▸ {topic}[/bold cyan]")
        console.print()
        
        for i, kp in enumerate(points, 1):
            # Summary
            console.print(f"    [white]{kp.summary}[/white]")
            
            # Original quote (truncated if too long)
            if kp.original_quote:
                quote = kp.original_quote
                if len(quote) > 200:
                    quote = quote[:200] + "..."
                console.print(f"    [dim italic]「{quote}」[/dim italic]")
            
            console.print()
    
    # Takeaways
    console.print(Panel(
        "\n".join(f"✓ {t}" for t in summary.takeaways),
        title="🎯 Takeaways",
        title_align="left",
        border_style="yellow",
        padding=(1, 2),
    ))
    
    console.print()


def display_summary_compact(summary: Summary, console: Console):
    """Display a compact version of the summary."""
    
    console.print(f"\n[bold]{summary.title}[/bold]\n")
    console.print(summary.overview)
    
    console.print("\n[bold]Key Points:[/bold]")
    for i, kp in enumerate(summary.key_points, 1):
        console.print(f"  {i}. {kp.summary}")
    
    console.print("\n[bold]Takeaways:[/bold]")
    for t in summary.takeaways:
        console.print(f"  • {t}")


def export_markdown(summary: Summary) -> str:
    """Export summary as Markdown."""
    lines = []
    
    # Title
    lines.append(f"# {summary.title}")
    lines.append("")
    
    # Overview
    lines.append("## Overview")
    lines.append("")
    lines.append(summary.overview)
    lines.append("")
    
    # Topics
    lines.append("## Topics")
    lines.append("")
    for topic in summary.topics:
        lines.append(f"- {topic}")
    lines.append("")
    
    # Key Points grouped by topic
    lines.append("## Key Points")
    lines.append("")
    
    # Group by topic
    topics_map = {}
    for kp in summary.key_points:
        if kp.topic not in topics_map:
            topics_map[kp.topic] = []
        topics_map[kp.topic].append(kp)
    
    for topic, points in topics_map.items():
        lines.append(f"### {topic}")
        lines.append("")
        
        for kp in points:
            lines.append(f"**{kp.summary}**")
            lines.append("")
            if kp.original_quote:
                lines.append(f"> {kp.original_quote}")
                lines.append("")
    
    # Takeaways
    lines.append("## Takeaways")
    lines.append("")
    for t in summary.takeaways:
        lines.append(f"- ✓ {t}")
    lines.append("")
    
    return "\n".join(lines)


def export_html(summary: Summary) -> str:
    """Export summary as a beautiful HTML page."""
    
    # Group key points by topic
    topics_map = {}
    for kp in summary.key_points:
        if kp.topic not in topics_map:
            topics_map[kp.topic] = []
        topics_map[kp.topic].append(kp)
    
    key_points_html = ""
    for topic, points in topics_map.items():
        points_html = ""
        for kp in points:
            quote_html = f'<blockquote class="quote">{kp.original_quote}</blockquote>' if kp.original_quote else ""
            points_html += f'''
            <div class="key-point">
                <p class="summary">{kp.summary}</p>
                {quote_html}
            </div>
            '''
        key_points_html += f'''
        <div class="topic-section">
            <h3 class="topic-title">{topic}</h3>
            {points_html}
        </div>
        '''
    
    topics_pills = " ".join(f'<span class="topic-pill">{t}</span>' for t in summary.topics)
    takeaways_html = "\n".join(f'<li>{t}</li>' for t in summary.takeaways)
    
    html = f'''<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{summary.title}</title>
    <style>
        :root {{
            --primary: #6366f1;
            --secondary: #8b5cf6;
            --accent: #06b6d4;
            --bg: #0f172a;
            --surface: #1e293b;
            --surface-hover: #334155;
            --text: #f1f5f9;
            --text-muted: #94a3b8;
            --border: #334155;
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.7;
            padding: 2rem;
        }}
        
        .container {{
            max-width: 900px;
            margin: 0 auto;
        }}
        
        h1 {{
            font-size: 2rem;
            margin-bottom: 2rem;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        
        .section {{
            background: var(--surface);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            border: 1px solid var(--border);
        }}
        
        .section-title {{
            font-size: 1.1rem;
            font-weight: 600;
            margin-bottom: 1rem;
            color: var(--accent);
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        
        .overview {{
            color: var(--text);
            white-space: pre-line;
        }}
        
        .topics-container {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
        }}
        
        .topic-pill {{
            background: var(--surface-hover);
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.875rem;
            color: var(--accent);
            border: 1px solid var(--border);
        }}
        
        .topic-section {{
            margin-bottom: 1.5rem;
        }}
        
        .topic-title {{
            font-size: 1rem;
            color: var(--secondary);
            margin-bottom: 0.75rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid var(--border);
        }}
        
        .key-point {{
            margin-bottom: 1rem;
            padding-left: 1rem;
            border-left: 3px solid var(--primary);
        }}
        
        .key-point .summary {{
            font-weight: 500;
            margin-bottom: 0.5rem;
        }}
        
        .quote {{
            font-style: italic;
            color: var(--text-muted);
            font-size: 0.9rem;
            padding: 0.5rem 1rem;
            background: rgba(99, 102, 241, 0.1);
            border-radius: 6px;
            margin: 0;
        }}
        
        .takeaways ul {{
            list-style: none;
        }}
        
        .takeaways li {{
            padding: 0.5rem 0;
            padding-left: 1.5rem;
            position: relative;
        }}
        
        .takeaways li::before {{
            content: "✓";
            position: absolute;
            left: 0;
            color: #22c55e;
            font-weight: bold;
        }}
        
        .footer {{
            text-align: center;
            color: var(--text-muted);
            font-size: 0.875rem;
            margin-top: 2rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📻 {summary.title}</h1>
        
        <div class="section">
            <div class="section-title">📝 Overview</div>
            <div class="overview">{summary.overview}</div>
        </div>
        
        <div class="section">
            <div class="section-title">🏷️ Topics</div>
            <div class="topics-container">
                {topics_pills}
            </div>
        </div>
        
        <div class="section">
            <div class="section-title">💡 Key Points</div>
            {key_points_html}
        </div>
        
        <div class="section takeaways">
            <div class="section-title">🎯 Takeaways</div>
            <ul>
                {takeaways_html}
            </ul>
        </div>
        
        <div class="footer">
            Generated by XYZ Transcript Download
        </div>
    </div>
</body>
</html>
'''
    return html


def list_summaries() -> list:
    """List all available summaries."""
    summaries_dir = DATA_DIR / "summaries"
    if not summaries_dir.exists():
        return []
    
    summaries = []
    for path in summaries_dir.glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                summaries.append({
                    "id": path.stem,
                    "title": data.get("title", "Unknown"),
                    "topics_count": len(data.get("topics", [])),
                    "key_points_count": len(data.get("key_points", [])),
                })
        except:
            pass
    
    return summaries
