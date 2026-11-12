"""Un module importé ne doit jamais être réassigné dans une fonction.

Sinon Python le traite comme une variable locale dans toute la fonction, et le premier
appel au module plante (UnboundLocalError) : c'est arrivé au flux le 12/11.
"""
import ast
import pathlib
import unittest

RACINE = pathlib.Path(__file__).resolve().parent.parent


class Ombres(unittest.TestCase):
    def test_aucun_module_masque(self):
        fautes = []
        for f in RACINE.rglob("*.py"):
            if ".git" in f.parts:
                continue
            arbre = ast.parse(f.read_text(encoding="utf-8"))
            modules = {(a.asname or a.name).split(".")[0]
                       for n in arbre.body if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
            for fn in ast.walk(arbre):
                if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    fautes += [f"{f.relative_to(RACINE)}:{n.lineno} {fn.name} réassigne {n.id}"
                               for n in ast.walk(fn)
                               if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store) and n.id in modules]
        self.assertEqual(fautes, [])


if __name__ == "__main__":
    unittest.main()
