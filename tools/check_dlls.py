from pathlib import Path
import pefile

base = Path('dist/SnipTranslate/_internal')
files = {p.name.lower(): p for p in base.rglob('*') if p.suffix.lower() in ('.dll', '.pyd')}
seen = set()
todo = [files['qtcore.pyd']]
while todo:
    path = todo.pop()
    if path in seen:
        continue
    seen.add(path)
    pe = pefile.PE(str(path))
    for dep in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
        other_path = files.get(dep.dll.decode().lower())
        if other_path is None:
            continue
        other = pefile.PE(str(other_path))
        exports = getattr(other, 'DIRECTORY_ENTRY_EXPORT', None)
        names = {s.name for s in exports.symbols} if exports else set()
        for symbol in dep.imports:
            if symbol.name and symbol.name not in names:
                print(path.name, other_path.name, symbol.name.decode())
        todo.append(other_path)
