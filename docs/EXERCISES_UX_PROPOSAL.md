# Propozycja przebudowy ćwiczeń

15 października 2026. Obejmuje opracowanie AI, bibliotekę ćwiczeń i rozwiązywanie. Dokument zapisuje propozycję poprzedzającą wdrożenie. Aktualny stan: [EXERCISES_UX_IMPLEMENTATION.md](EXERCISES_UX_IMPLEMENTATION.md).

## Diagnoza

Kod i podgląd na syntetycznych danych pokazują trzy różne czynności wymieszane w podobnych kartach: sprawdzanie propozycji AI, zarządzanie bankiem pytań i odpowiadanie podczas sesji. Użytkownik powinien zawsze wiedzieć, którą z nich wykonuje.

- Biblioteka podkreśla „Dodaj ćwiczenie”, „Edytuj” i „Archiwizuj”. Poszczególne pytanie nie ma akcji rozpoczęcia praktyki. Nagłówek „Ucz się / sprawdź się” prowadzi do kolejnego konfiguratora.
- Pięć sekcji według rodzaju i dwukolumnowa siatka tworzą puste miejsca przy małych zestawach. Przełączniki typów tylko przewijają stronę; nie filtrują listy.
- Biblioteka nie pokazuje wariantów quizu. Podgląd AI udostępnia je dopiero w edycji jako tekst.
- Podgląd AI wyświetla polecenie jako zwykły tekst, podczas gdy sesja korzysta z renderera Markdown i matematyki. To niespójność szczególnie widoczna w zadaniach z kodem i wzorami.
- „Sprawdź odpowiedź i edytuj” łączy odczyt wzorca z długim formularzem: polecenie, warianty, wyjaśnienie, kryteria i odpowiedź.
- W części interfejsu etykiety mają 10–12 px, opis samooceny 9 px. Najważniejsze działanie sesji może znajdować się poniżej pierwszego ekranu nawet przy krótkim pytaniu.
- Błędny quiz używa tego samego zielonego panelu odpowiedzi co poprawny. Wybrane warianty znikają po sprawdzeniu, więc trudniej porównać błąd z prawidłowym wyborem.
- Kliknięcie sprawdzenia zapisuje ujawnienie i odpowiedź, ale ocenę quizu dopiero kolejny przycisk. Użytkownik musi odróżniać szkic, sprawdzenie i zapis wyniku.
- Pytanie, odpowiedź użytkownika, wzorzec, objaśnienie i samoocena tworzą długą kolumnę. Dodatkowe metadane nad pytaniem zajmują uwagę i miejsce.

## 1. Sprawdzanie materiałów AI

Nagłówek: „Sprawdź ćwiczenia od AI”. Obok liczba wybranych do zapisania, np. „Wybrane 12 z 16”. To jasno określa znaczenie checkboxów.

Domyślnie jedna lista. Każdy element zawiera kolejny numer, krótki podgląd polecenia, rodzaj oraz przełącznik „Zachowaj”. Wyszukiwanie i prawdziwy filtr rodzaju ograniczają zestaw. Powiązany rozdział pomaga ocenić zakres; rodzaj ćwiczenia nie musi określać kolejności całej strony.

Rozwinięcie pokazuje czytelny podgląd polecenia, wariantów quizu, odpowiedzi i wyjaśnienia. Ten sam renderer co podczas nauki obsługuje wzory, kod, listy i tabele. Warianty są podglądem, bez kontrolek sugerujących rozwiązywanie quizu. „Edytuj” jest osobną akcją otwierającą formularz tylko dla tego pytania.

Na dole widoczna akcja „Zapisz 12 ćwiczeń”, aktualizowana po zaznaczeniach. Osobne zaznaczenie notatki pozostaje czytelne. Pasek nie może zasłaniać treści ani nawigacji telefonu. Stan edycji i wybór pytań muszą przetrwać błąd walidacji.

## 2. Biblioteka zestawu

Główna akcja: „Rozpocznij ćwiczenia”. Obok „Sprawdzian”; konfiguracja zakresu i czasu jako dodatkowe ustawienia. W kontekście AI rozbudowa banku prowadzi do „Wygeneruj więcej z materiału”. Dla tematu bez oryginalnego pliku akcja prosi o jego dodanie, zamiast sugerować, że generowanie jest już możliwe.

Jedna lista pytań z filtrami „Wszystkie”, „Do powtórki”, „Nowe” i rodzajem. Rozwinięte pytanie pokazuje pełną treść i „Rozwiąż to pytanie”; odpowiedź jest świadomie odsłaniana przez osobną akcję. Ujawnienie odpowiedzi na liście nie nalicza oceny. Edycja, przenoszenie i archiwizacja trafiają do menu dodatkowych działań.

Obsługa pojedynczego pytania wymaga jawnego zakresu sesji opartego na jego ID. Nie może po cichu rozpoczynać całego tematu. Ćwiczenia z dłuższym poleceniem nie mogą być ucinane po otwarciu.

## 3. Rozwiązywanie

Jeden ekran ma jedną główną decyzję. Góra pokazuje „Pytanie 3 z 12” i przerwę. Temat, źródła, szacunkowy czas oraz dodatkowe informacje są drugorzędne. Pytanie jest najważniejszą treścią; polecenia z kilkoma akapitami korzystają z normalnej typografii treści zamiast całego bloku pogrubionego nagłówka.

- Quiz: pełne warianty A–D, duży obszar wyboru, jeden przycisk „Sprawdź”. Po sprawdzeniu zaznaczony wariant zostaje. Tekst i symbol wskazują poprawność niezależnie od koloru. Wynik zapisuje się atomowo przy sprawdzeniu, a „Następne” jedynie przechodzi dalej. Muszą pozostać idempotencja i cofnięcie oceny.
- Fiszka: pytanie → „Pokaż odpowiedź” → samoocena. Bez niepotrzebnego pola tekstowego.
- Luka: krótkie pole odpowiedzi, a następnie porównanie. Nie obiecywać automatycznej oceny odmiany lub synonimów, jeśli backend jej nie wykonuje.
- Pytanie otwarte i zadanie: odpowiedź tekstowa albo łatwy wybór „Na kartce / ustnie”. Ten wybór ukrywa zbędne pole. Nie wymaga wpisywania „nie wiem”; osobna akcja pozwala przejść do wyjaśnienia i oznacza próbę jako niesamodzielną.
- Podpowiedź i źródło są dostępne na żądanie. Użycie pomocy nadal jest zapisywane automatycznie.

Po odpowiedzi główna treść to wynik quizu albo porównanie własnej odpowiedzi ze wzorcem. Dłuższe wyjaśnienie i źródło są rozwijane. Samoocena odpowiedzi otwartych nie może wyglądać jak werdykt AI.

Rekomendacja do sprawdzenia z użytkownikami: trzy odpowiedzi samooceny „Nie umiem jeszcze”, „Częściowo”, „Samodzielnie”. To zmiana zachowania produktu, więc wymaga jawnego mapowania do obecnych ocen i zachowania historii; istniejącej oceny „Łatwo” nie należy usuwać z danych. Alternatywa o mniejszym zakresie: zachować cztery oceny i poprawić etykiety oraz czytelność.

Na telefonie główne działanie może pozostać dostępne przy dolnej krawędzi, z miejscem na dolną nawigację i klawiaturę. Nie wolno utrudniać czytania wyjaśnienia, powiększania ani przewijania długiego zadania.

## 4. Rola AI

Najpierw poprawić sposób prezentacji istniejących ćwiczeń. Dalsza pomoc AI powinna dotyczyć konkretnego pytania: „Wyjaśnij prościej” lub „Pokaż przykład”. To osobny etap wymagający działającego połączenia i jawnego uruchomienia; nie ma potrzeby umieszczać kolejnego ogólnego czatu obok każdego zadania.

Generowanie powinno preferować jeden sprawdzalny zamiar w pytaniu, osobne polecenie i wyjaśnienie, jednoznaczne warianty oraz powiązanie ze źródłem. Długie zadanie rachunkowe nie powinno być automatycznie skracane kosztem potrzebnych danych. Ocena jakości pytań wymaga osobnego sprawdzenia prawdziwego opracowania AI.

## Kolejność realizacji

1. Wspólny podgląd treści i jedna lista, czytelne quizy, osobny podgląd/edycja, uporządkowane główne działania.
2. Przebudowa sesji, jednoznaczny wynik quizu, zapis przy sprawdzeniu i czytelne porównanie odpowiedzi.
3. Filtry, pojedyncze pytanie, zaznaczanie i pasek zapisu propozycji AI.
4. Weryfikacja sposobu samooceny z użytkownikami; dopiero potem kontekstowa pomoc AI.

## Kryteria odbioru

- Przed odpowiedzią i po niej widać, co zrobić dalej i co zostało zapisane.
- Ten sam wzór, tabela i kod wyglądają zgodnie w podglądzie AI, bibliotece i sesji.
- Czytanie odpowiedzi nie wymaga otwierania formularza edycji.
- Poprawny i błędny wynik są rozpoznawalne po treści i symbolu, nie tylko po kolorze.
- Quiz nie wymaga drugiej decyzji o zapisaniu obiektywnego wyniku.
- Przycisk pojedynczego pytania uruchamia wyłącznie to pytanie.
- Przerwa, powtórzony zapis, cofnięcie i migawki historycznych sesji nadal działają; sprawdzian nie ujawnia odpowiedzi przed końcem.
- Sprawdzenie przy 390 px, powiększeniu tekstu, obsłudze klawiaturą i długich materiałach z matematyką. Testy samej liczby kliknięć nie zastępują obserwacji studentów.

## Podstawa analizy

Przejrzano topic.html, upload_preview.html, study.html, exam.html, review_fields.html, macros.html, learning_help.html, style i obsługę zapisu w study.py. W osobnej bazie demonstracyjnej sprawdzono listę, błędny quiz i pytanie otwarte przy szerokości 390 px. Nie modyfikowano materiałów użytkownika, nie wysyłano danych do AI ani nie wdrażano tej propozycji.

Zrzuty stanu przed zmianami: output/student-workflow/exercises-before-list.png, exercises-before-feedback.png, exercises-before-mobile.png.
