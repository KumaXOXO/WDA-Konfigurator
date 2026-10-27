#!/usr/bin/env python3
"""Derive locales/pt-PT.json from pt-BR.json (only the entries that differ, with _fallback pt-BR).

Replaces typical Brazilian terms with European Portuguese ones. Review the result by hand.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PHRASES = [  # longer phrases first (gender changes)
    ("aplicativo aberto", "aplicação aberta"), ("podem se conectar", "podem ligar-se"),
    ("detectado", "detetado"), ("em uma", "numa"),
    ("este aplicativo", "esta aplicação"), ("Este aplicativo", "Esta aplicação"),
    ("do aplicativo", "da aplicação"), ("no aplicativo", "na aplicação"), ("ao aplicativo", "à aplicação"),
    ("o aplicativo", "a aplicação"), ("O aplicativo", "A aplicação"), ("aplicativo", "aplicação"),
    ("Mantenha pressionado", "Mantenha premido"), ("Pressione", "Prima"), ("pressione", "prima"),
    ("conecte-se", "ligue-se"), ("Conecte-se", "Ligue-se"), ("Conectar-se", "Ligar-se"),
    ("desconecte", "desligue"), ("Desconecte", "Desligue"),
    # "tela" (f.) → "ecrã" (m.)
    ("na tela", "no ecrã"), ("à tela", "ao ecrã"), ("da tela", "do ecrã"), ("A tela", "O ecrã"),
    ("a tela", "o ecrã"), ("conexão com a Internet", "ligação à Internet"), ("controle", "controlo"),
]
WORDS = {
    "senha": "palavra-passe", "Senha": "Palavra-passe", "senhas": "palavras-passe", "Senhas": "Palavras-passe",
    "arquivo": "ficheiro", "Arquivo": "Ficheiro", "arquivos": "ficheiros",
    "tela": "ecrã", "Tela": "Ecrã", "Registro": "Registo", "registro": "registo", "email": "e-mail",
    "conectar": "ligar", "Conectar": "Ligar", "conecte": "ligue", "Conecte": "Ligue",
    "conectado": "ligado", "Conectado": "Ligado", "conecta": "liga",
    "conexão": "ligação", "Conexão": "Ligação",
}
NO_GERUND = {"quando", "Quando", "comando"}


def gerund(m):
    word = m.group(0)
    if word in NO_GERUND:
        return word
    stem, end = word[:-4], word[-4:]
    inf = stem + {"ando": "ar", "endo": "er", "indo": "ir"}[end]
    return ("A " + inf[0].lower() + inf[1:]) if word[0].isupper() else ("a " + inf)


def convert(text):
    for a, b in PHRASES:
        text = text.replace(a, b)
    text = re.sub(r"\b\w+(?:ando|endo|indo)\b", gerund, text)
    return re.sub(r"\b\w+\b", lambda m: WORDS.get(m.group(0), m.group(0)), text)


br = json.loads((ROOT / "locales" / "pt-BR.json").read_text(encoding="utf-8"))
pt = {"_fallback": "pt-BR"}
for k, v in br.items():
    c = convert(v)
    if c != v:
        pt[k] = c
(ROOT / "locales" / "pt-PT.json").write_text(json.dumps(pt, ensure_ascii=False, indent=0), encoding="utf-8")
print(f"pt-PT: {len(pt) - 1} entries differ from pt-BR")
