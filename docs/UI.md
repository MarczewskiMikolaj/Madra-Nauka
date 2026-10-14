# Odświeżenie interfejsu

Kierunek: spokojne miejsce do pracy z materiałem. Krótkie instrukcje, wyraźny następny krok i edycja rozwijana wtedy, gdy jest potrzebna.

- Paleta: tło `#f4f6f9`, powierzchnia `#ffffff`, tekst `#1c2944`, tekst pomocniczy `#667287`, akcje `#304bdb`, przykład materiału `#eaf0f8`.
- Typografia: Avenir Next z systemowymi zamiennikami. Nagłówki 28–36 px, tekst 13–15 px, mniejszy tekst dla metadanych. Opisy mieszczą się w krótkich kolumnach.
- Połączenie AI: status konta i główna akcja w lewej kolumnie, jawnie oznaczony przykład opracowania w prawej. Szczegóły udostępniania danych rozwijane pod spodem.
- Wgrywanie: duża dostępna klawiaturą strefa wyboru lub przeciągnięcia pliku, nazwa i rozmiar po wyborze, krótka instrukcja przebiegu obok formularza.
- Opracowanie: cel i generowanie oddzielone od edycji notatki. Ćwiczenia w siatce; odpowiedzi i pola edycji rozwijane osobno. Oryginalne źródło dostępne przez rozwinięcie oraz pobranie.
- Nawigacja: połączenie AI dostępne w głównym menu, skrót do wgrywania w nagłówku; pięć pozycji na telefonie.

Weryfikacja: 50 testów integracyjnych, sprawdzenie składni JavaScript, ręczny przegląd screenshotów w Chromium dla 1440 px i 390 px. Przetestowano wybór i przeciąganie pliku, edycję rozwijanego ćwiczenia, odznaczenie propozycji i zapis materiałów. Sprawdzone widoki mobilne nie mają przewijania w poziomie. Zrzuty lokalnie w `output/playwright/ui-*.png` (ignorowane przez Git).

## Rozbudowa przebiegu studenta — 13 października 2026

Wspólny język paneli i formularzy obejmuje teraz wybór trybu sesji, konflikt i przerwę, podpowiedzi, kryteria oceny, pełny przegląd odpowiedzi, sprawdzian i importy. Zakres celu wskazuje nowe/trudne ćwiczenia i tematy niesprawdzone. Czytnik notatek renderuje Markdown, lokalne wzory, tabele oraz bloki kodu. Sprawdzian nie pokazuje pomocy ani źródeł przed zakończeniem.

Sprawdzono Chromium 1440 px i 390 px, m.in. `output/playwright/student/note-desktop.png`, `goals-mobile.png`, `feedback-mobile.png`, `review-mobile.png`, `exam-results-mobile.png`. Sprawdzone widoki mobilne nie mają przewijania dokumentu w poziomie. Konsola bez błędów i ostrzeżeń.
