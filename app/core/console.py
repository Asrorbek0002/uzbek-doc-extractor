# -*- coding: utf-8 -*-
"""Pretty, uniform terminal output.

EVERY script in the project uses this module — so the output has one style and
taking a screenshot for a report is easy.

Colors are only written to a real terminal: with `> log.txt` no ANSI codes are
emitted and the log file stays clean.
"""
from __future__ import annotations

import os
import shutil
import sys
import time

ENI = min(shutil.get_terminal_size((78, 24)).columns, 78)
_RANG = sys.stdout.isatty() and os.getenv("NO_COLOR") is None


def _r(kod: str, matn: str) -> str:
    return f"\033[{kod}m{matn}\033[0m" if _RANG else matn


def kuchli(m):  return _r("1", m)       # bold
def kul(m):     return _r("90", m)      # grey
def yashil(m):  return _r("32", m)      # green
def qizil(m):   return _r("31", m)      # red
def sariq(m):   return _r("33", m)      # yellow
def kok(m):     return _r("36", m)      # cyan

OK, XATO, OGOH, NUQTA = "✓", "✗", "!", "·"


def sarlavha(matn: str) -> None:
    """A main heading in a heavy frame."""
    print()
    print(kok("┌" + "─" * (ENI - 2) + "┐"))
    print(kok("│") + kuchli(f" {matn}".ljust(ENI - 2)) + kok("│"))
    print(kok("└" + "─" * (ENI - 2) + "┘"))


def bolim(matn: str) -> None:
    """A small section separator."""
    print()
    print(kuchli(matn) + " " + kul("─" * max(ENI - len(matn) - 2, 0)))


def maydon(nom: str, qiymat, holat: bool | None = None, izoh: str = "") -> None:
    """An aligned `name : value` line, optionally with a ✓/✗ mark."""
    belgi = ""
    if holat is True:
        belgi = yashil(f" {OK}")
    elif holat is False:
        belgi = qizil(f" {XATO}")
    chap = f"  {nom:<26}"
    print(f"{chap}{kul(':')} {qiymat}{belgi}" + (f"  {kul(izoh)}" if izoh else ""))


def jadval(sarlavhalar: list[str], qatorlar: list[list], ongga: set[int] | None = None) -> None:
    """A plain aligned table. `ongga` — indexes of the right-aligned columns."""
    ongga = ongga or set()
    qat = [[str(x) for x in q] for q in qatorlar]
    kengliklar = [
        max(len(sarlavhalar[i]), *(len(q[i]) for q in qat)) if qat else len(sarlavhalar[i])
        for i in range(len(sarlavhalar))
    ]

    def satr(hujayralar, bezak=lambda x: x):
        qismlar = [
            (h.rjust(kengliklar[i]) if i in ongga else h.ljust(kengliklar[i]))
            for i, h in enumerate(hujayralar)
        ]
        print("  " + bezak("  ".join(qismlar)))

    satr(sarlavhalar, kuchli)
    print("  " + kul("  ".join("─" * k for k in kengliklar)))
    for q in qat:
        satr(q)


def natija(muvaffaq: bool, matn: str) -> None:
    print()
    if muvaffaq:
        print("  " + yashil(f"{OK} {matn}"))
    else:
        print("  " + qizil(f"{XATO} {matn}"))


def ogohlantirish(matn: str) -> None:
    print("  " + sariq(f"{OGOH} {matn}"))


def eslatma(matn: str) -> None:
    print("  " + kul(f"{NUQTA} {matn}"))


class Jarayon:
    """A progress indicator that updates in place on one line.

        with Jarayon("embed", 3048) as j:
            for ...:
                j.qadam(16)
    """

    def __init__(self, nom: str, jami: int, qadamda: int = 20):
        self.nom, self.jami, self.qadamda = nom, jami, qadamda
        self.hozir = 0
        self.t0 = time.perf_counter()
        self._n = 0
        self._tugadi = False

    def __enter__(self):
        return self

    def qadam(self, nechta: int = 1) -> None:
        self.hozir = min(self.hozir + nechta, self.jami)
        self._n += 1
        if self._n % self.qadamda == 0 or self.hozir >= self.jami:
            self._chiz()
            if self.hozir >= self.jami:
                self._tugadi = True

    def _chiz(self) -> None:
        # Outside a terminal (when written to a log file) `\r` does not work and
        # the output turns into noise — so only one final line is printed.
        if not _RANG and self.hozir < self.jami:
            return
        ulush = self.hozir / max(self.jami, 1)
        kenglik = 28
        tola = int(kenglik * ulush)
        chiziq = "█" * tola + kul("░" * (kenglik - tola))
        ketgan = time.perf_counter() - self.t0
        tezlik = self.hozir / max(ketgan, 1e-9)
        satr = (f"  {self.nom:<10} {chiziq} {self.hozir:>6}/{self.jami}"
                f"  {kul(f'{tezlik:.0f}/s  {ketgan:.1f}s')}")
        print("\r" + " " * ENI + "\r" + satr, end="", flush=True)

    def yakunla(self) -> None:
        """Draw the final state and close the line (never drawn twice)."""
        if not self._tugadi:
            self._chiz()
        print()

    def __exit__(self, *a):
        self.yakunla()


def vaqt(sekund: float) -> str:
    """Render a number of seconds in a readable form."""
    if sekund < 1:
        return f"{sekund * 1000:.0f} ms"
    if sekund < 60:
        return f"{sekund:.1f} s"
    return f"{int(sekund // 60)}m {sekund % 60:.0f}s"
