#!/usr/bin/env python3
"""
taiga_get_project_id.py
-----------------------
Recupera l’ID d’un projecte a Taiga Cloud a partir del seu *slug* o del nom
visible (display name).

Ús bàsic
========
1. Quan ja coneixes el *slug* exacte
   python taiga_get_project_id.py --slug slushee-a-chopchop-amep \
                                  --user TU_USUARI --password LA_PASS

2. Quan només coneixes el nom (insensible a majúscules/minúscules)
   python taiga_get_project_id.py --name "Slushee-A ChopChop AMEP" \
                                  --user TU_USUARI --password LA_PASS

També pots establir les credencials via variables d’entorn:
   export TAIGA_USERNAME=TU_USUARI
   export TAIGA_PASSWORD=LA_PASS
   python taiga_get_project_id.py --slug slushee-a-chopchop-amep
"""

import argparse
import os
import sys
import requests
from typing import List, Dict

API_BASE = "https://api.taiga.io/api/v1"





def get_by_slug(slug: str, token: str) -> Dict:
    """Retorna el JSON del projecte pel seu slug (una sola petició)."""
    h = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{API_BASE}/projects/by_slug", headers=h,
                     params={"slug": slug}, timeout=10)
    if r.status_code == 404:
        sys.exit(f"Slug «{slug}» no existeix o no és visible per aquest usuari.")
    r.raise_for_status()
    return r.json()


def list_user_projects(token: str) -> List[Dict]:
    """Llista tots els projectes on l’usuari autenticat és membre."""
    h = {
        "Authorization": f"Bearer {token}",
        "x-disable-pagination": "True",   # rebem tot en una sola resposta
    }
    r = requests.get(f"{API_BASE}/projects", headers=h,
                     params={"member": "me"}, timeout=10)
    r.raise_for_status()
    return r.json()


def find_by_name(name: str, projects: List[Dict]) -> Dict:
    """
    Cerca (case-insensitive) un projecte dins la llista `projects`
    que tingui display name exactament igual a `name`.
    """
    name_lower = name.lower()
    # Iterem sobre TOTES les entrades, imprimint-les perquè vegis el procés
    for p in projects:
        print(f"DEBUG  project candidate: {p['name']}  (slug={p['slug']})")
        if p["name"].lower() == name_lower:
            return p
    sys.exit(f"No project amb nom «{name}» trobat a la teva llista d’adhesions.")


def main(argv: List[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description="Fetch Taiga project id by slug or by display name."
    )
    ap.add_argument("--slug", help="Slug exacte del projecte (mètode preferit).")
    ap.add_argument("--name",
                    help="Nom visible del projecte (case-insensitive). S'usa si --slug no és present.")
    ap.add_argument("--user", default=os.getenv("TAIGA_USERNAME"),
                    help="Usuari Taiga (o variable d’entorn TAIGA_USERNAME).")
    ap.add_argument("--password", default=os.getenv("TAIGA_PASSWORD"),
                    help="Contrasenya Taiga (o variable d’entorn TAIGA_PASSWORD).")
    args = ap.parse_args(argv)

    # Validacions bàsiques
    if not (args.slug or args.name):
        ap.error("Cal indicar --slug o --name")

    if not (args.user and args.password):
        ap.error("Credencials requerides: --user/--password o variables env TAIGA_USERNAME/TAIGA_PASSWORD")


    # 2. Recuperació del projecte
    if args.slug:
        project = get_by_slug(args.slug)
    else:
        projects = list_user_projects(token)
        # Imprimim totes les opcions (sense ometre elements) perquè vegis què rep
        for idx, proj in enumerate(projects, start=1):
            print(f"[{idx}] {proj['name']} (slug={proj['slug']}, id={proj['id']})")
        project = find_by_name(args.name, projects)

    # 3. Resultat final
    print("\n===== RESULTAT =====")
    print(f"Nom del projecte : {p
