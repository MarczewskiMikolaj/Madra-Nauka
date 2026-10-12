import json
import secrets
from datetime import timedelta
from uuid import uuid4
from werkzeug.security import generate_password_hash
from ..db import transaction
from .learning import KIND_DIMENSION, now_iso, today_date


def create_demo():
    uid = uuid4().hex
    now = now_iso()
    subjects = [
        (
            "Biologia",
            "Zrozumieć procesy, a nie tylko zapamiętać nazwy.",
            "green",
            [
                (
                    "Komórka i energia",
                    "Od budowy komórki do produkcji ATP.",
                    "Mitochondrium wytwarza ATP podczas oddychania komórkowego. Chloroplast przekształca energię światła w energię chemiczną.\n\nPomyśl o komórce jak o współpracujących układach: każda struktura pełni swoją funkcję.",
                    [
                        (
                            "open",
                            "Dlaczego komórki mięśniowe potrzebują wielu mitochondriów?",
                            "Praca mięśni wymaga dużo ATP. Mitochondria produkują ATP w oddychaniu komórkowym, dlatego komórki o wysokim zapotrzebowaniu na energię mają ich więcej.",
                            3,
                            [],
                        ),
                        (
                            "flashcard",
                            "Jaka jest podstawowa funkcja mitochondrium?",
                            "Produkcja ATP w procesie oddychania komórkowego.",
                            1,
                            [],
                        ),
                        (
                            "quiz",
                            "Gdzie w komórce roślinnej zachodzi fotosynteza?",
                            "W chloroplastach",
                            1,
                            [
                                "W mitochondriach",
                                "W chloroplastach",
                                "W jądrze komórkowym",
                                "W rybosomach",
                            ],
                        ),
                        (
                            "exercise",
                            "Porównaj mitochondrium i chloroplast. Podaj po jednej wspólnej cesze i różnicy.",
                            "Wspólna cecha: oba organella mają własne DNA i podwójną błonę. Różnica: mitochondrium uczestniczy w oddychaniu, chloroplast w fotosyntezie.",
                            4,
                            [],
                        ),
                        (
                            "cloze",
                            "Podstawową jednostką strukturalną i funkcjonalną organizmów jest [...].",
                            "komórka",
                            1,
                            [],
                        ),
                    ],
                ),
                (
                    "Genetyka",
                    "Od DNA do białka.",
                    "DNA przechowuje informację genetyczną. Transkrypcja tworzy RNA na matrycy DNA. Translacja wykorzystuje informację mRNA do syntezy białka.",
                    [
                        (
                            "open",
                            "Czym różni się transkrypcja od translacji?",
                            "Transkrypcja to synteza RNA na matrycy DNA. Translacja to synteza białka na podstawie sekwencji mRNA.",
                            3,
                            [],
                        ),
                        (
                            "flashcard",
                            "Co oznacza skrót DNA?",
                            "Kwas deoksyrybonukleinowy.",
                            1,
                            [],
                        ),
                        (
                            "exercise",
                            "Wyjaśnij, dlaczego zmiana jednego nukleotydu nie zawsze zmienia białko.",
                            "Kod genetyczny jest zdegenerowany: różne kodony mogą kodować ten sam aminokwas. Zmiana może też wystąpić poza regionem kodującym.",
                            4,
                            [],
                        ),
                    ],
                ),
            ],
        ),
        (
            "Python",
            "Od rozumienia kodu do samodzielnego rozwiązywania zadań.",
            "blue",
            [
                (
                    "Kolekcje i pętle",
                    "Listy, słowniki i przetwarzanie danych.",
                    "Lista przechowuje uporządkowaną kolekcję elementów. Słownik mapuje klucze na wartości. List comprehension pozwala tworzyć listę na podstawie istniejącej kolekcji.",
                    [
                        (
                            "exercise",
                            "Napisz wyrażenie, które z listy [1, 2, 3, 4, 5, 6] utworzy listę kwadratów liczb parzystych.",
                            "[x ** 2 for x in [1, 2, 3, 4, 5, 6] if x % 2 == 0]\nWynik: [4, 16, 36].",
                            4,
                            [],
                        ),
                        (
                            "quiz",
                            "Który typ służy do mapowania kluczy na wartości?",
                            "dict",
                            1,
                            ["list", "tuple", "dict", "set"],
                        ),
                        (
                            "open",
                            "Dlaczego użycie set może ułatwić usunięcie duplikatów?",
                            "Set przechowuje unikalne elementy. Zbudowanie zbioru z kolekcji usuwa powtórzenia, ale nie zachowuje pozycji elementów jako część kontraktu typu.",
                            2,
                            [],
                        ),
                        (
                            "cloze",
                            "Aby przejść po kluczach i wartościach słownika, użyj metody [...].",
                            "items()",
                            1,
                            [],
                        ),
                    ],
                )
            ],
        ),
        (
            "Angielski",
            "Ćwiczyć znaczenie i używać języka w kontekście.",
            "purple",
            [
                (
                    "Everyday English",
                    "Małe rozmowy, naturalne zdania.",
                    "Present perfect łączy przeszłe doświadczenia z teraźniejszością. Używamy have/has i trzeciej formy czasownika. Przykład: I have visited London.",
                    [
                        (
                            "cloze",
                            "She [...] already finished her homework.",
                            "has",
                            1,
                            [],
                        ),
                        (
                            "open",
                            "Napisz dwa zdania o swoich doświadczeniach, używając present perfect.",
                            "Przykłady: I have learned a new skill. I have visited another country. Sprawdź konstrukcję have/has + past participle.",
                            3,
                            [],
                        ),
                        (
                            "flashcard",
                            "Co oznacza „to figure out”?",
                            "Rozgryźć, zrozumieć lub znaleźć rozwiązanie.",
                            1,
                            [],
                        ),
                    ],
                )
            ],
        ),
    ]
    with transaction() as db:
        db.execute(
            "INSERT INTO users VALUES (?,?,?,1,?)",
            (
                uid,
                "demo-" + uid[:10],
                generate_password_hash(secrets.token_hex(20)),
                now,
            ),
        )
        index = 0
        first_wid = None
        for name, description, color, topics in subjects:
            wid = uuid4().hex
            first_wid = first_wid or wid
            db.execute(
                "INSERT INTO workspaces VALUES (?,?,?,?,?,?,NULL)",
                (wid, uid, name, description, color, now),
            )
            for name, description, note, activities in topics:
                tid = uuid4().hex
                db.execute(
                    "INSERT INTO topics VALUES (?,?,?,?,?)",
                    (tid, wid, name, description, now),
                )
                db.execute(
                    "INSERT INTO materials VALUES (?,?,'note',?,?,?,?)",
                    (uuid4().hex, tid, "Najważniejsze idee", note, now, now),
                )
                for kind, prompt, answer, minutes, options in activities:
                    aid = uuid4().hex
                    db.execute(
                        "INSERT INTO activities VALUES (?,?,?,?,?,?,?,?,0,NULL,?,?)",
                        (
                            aid,
                            tid,
                            kind,
                            KIND_DIMENSION[kind],
                            prompt,
                            answer,
                            json.dumps(options),
                            minutes,
                            now,
                            now,
                        ),
                    )
                    if index in (0, 1, 2, 8):
                        db.execute(
                            "INSERT INTO progress VALUES (?,?,1,1,2,3,?,?)",
                            (
                                uid,
                                aid,
                                (today_date() - timedelta(days=1)).isoformat(),
                                now,
                            ),
                        )
                    elif index in (6, 11):
                        db.execute(
                            "INSERT INTO progress VALUES (?,?,1,1,2,3,?,?)",
                            (
                                uid,
                                aid,
                                (today_date() + timedelta(days=3)).isoformat(),
                                now,
                            ),
                        )
                    index += 1
        db.execute(
            "INSERT INTO goals VALUES (?,?,?,?,?,?,0,?)",
            (
                uuid4().hex,
                uid,
                first_wid,
                "Sprawdzian z biologii",
                (today_date() + timedelta(days=21)).isoformat(),
                20,
                now,
            ),
        )
    return uid
