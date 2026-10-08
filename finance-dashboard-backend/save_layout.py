import sys
from app.pdf_parser import extract_layout_pages

pages = extract_layout_pages(open(sys.argv[1], "rb").read())
with open("layout.txt", "w", encoding="utf-8") as f:
    f.write("\n=====PAGE BREAK=====\n".join(pages))
print(f"Wrote layout.txt ({len(pages)} page(s)). Open it in Notepad or VS Code, not Word.")