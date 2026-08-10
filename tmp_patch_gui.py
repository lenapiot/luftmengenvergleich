from pathlib import Path

path = Path("ui/gui.py")
text = path.read_text(encoding="utf-8")
start = text.index("def create_file_selection_row(")
end = text.index("def start_gui() -> None:")
block = text[start:end]
# Indent every top-level definition line in the block by 4 spaces.
lines = block.splitlines(keepends=True)
new_lines = [('    ' + line) if line.startswith('def ') else line for line in lines]
new_text = text[:start] + ''.join(new_lines) + text[end:]
path.write_text(new_text, encoding="utf-8")
print('patched')
