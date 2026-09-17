import sys
import json
from ddgs import DDGS

def search(query, max_results=5):
    try:
        ddgs = DDGS()
        results = list(ddgs.text(query, max_results=max_results))
        return results
    except Exception as e:
        print(f"Error en búsqueda: {e}", file=sys.stderr)
        return []

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python search.py \"tu consulta\" [max_results]")
        sys.exit(1)
        
    q = sys.argv[1]
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    
    res = search(q, count)
    for idx, r in enumerate(res, 1):
        print(f"[{idx}] {r.get('title', 'Sin título')}")
        print(f"    URL: {r.get('href', '')}")
        print(f"    {r.get('body', '')}\n")
