"""Run the standalone GUI or pass CLI options to the normalisation script."""
from pathlib import Path
import runpy
import sys

def main():
    recovery = runpy.run_path(str(Path(__file__).resolve().parent / '_normokontrol_recovery.py'))
    recovery['recover'](Path(__file__).resolve().parent)
    if '--mcp' in sys.argv[1:]:
        if sys.argv[1:] != ['--mcp']:
            raise SystemExit('--mcp используется отдельно; аргументы передаются через MCP tools/call.')
        from scripts.agent_mcp import serve
        for stream in (sys.stdin, sys.stdout, sys.stderr):
            if stream and hasattr(stream, 'reconfigure'):
                stream.reconfigure(encoding='utf-8')
        serve()
        raise SystemExit(0)
    if '--agent' in sys.argv[1:] or any(arg.startswith('--agent=') for arg in sys.argv[1:]):
        from scripts.agent_api import cli_main
        if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if sys.stdin and hasattr(sys.stdin, 'reconfigure'):
            sys.stdin.reconfigure(encoding='utf-8')
        if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
        raise SystemExit(cli_main())
    runpy.run_path(str(Path(__file__).resolve().parent / "scripts" / "normokontrol.py"), run_name="__main__")


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        if not sys.argv[1:] or '--gui' in sys.argv[1:]:
            from scripts.startup_errors import show_startup_error
            show_startup_error(error, Path(__file__).resolve().parent)
            raise SystemExit(1)
        raise
