# Mądra Nauka — audyt użyteczności dla studenta

15 października 2026. Ocena bieżącej aplikacji `madra/`, po wdrożeniu rozbudowy opisanej w `STUDENT_IMPLEMENTATION_PLAN.md`.

## Wniosek

Projekt ma już spójny fundament do samodzielnej nauki: materiały, różne ćwiczenia, informację zwrotną, powtórki i próbny sprawdzian. Największą korzyść przyniesie teraz skrócenie drogi od materiałów z uczelni do pierwszej wartościowej sesji, zachowanie pracy podczas przerw oraz połączenie celów w jeden plan dnia.

Obecna aplikacja najlepiej odpowiada osobie, która umie przygotować własne pytania lub korzysta z połączenia ChatGPT, pracuje głównie na treści tekstowej i wybiera jeden dominujący cel. Student mający kilka egzaminów, dużo slajdów, zadania rozwiązywane na kartce i krótkie sesje na telefonie napotka więcej przeszkód.

To audyt ekspercki i symulacje użytkowania, a nie badanie rzeczywistych studentów. Nie potwierdza skuteczności dydaktycznej aplikacji ani jakości prawdziwych opracowań AI.

## Zakres i weryfikacja

- Przejrzano aktywne moduły, szablony, obsługę materiałów, importy, planowanie, sesje, statystyki, ustawienia oraz dokumentację. `legacy/` jest archiwum, nie bieżącą aplikacją.
- Istniejący `graphify-out/graph.json` opisuje dawną strukturę projektu; nie użyto go jako dowodu zachowania nowej aplikacji.
- Uruchomiono lokalną aplikację z osobną bazą w `/private/tmp/madra-student-audit-20261015/`, bez połączenia z chmurą i prawdziwym kontem AI.
- W przeglądarce sprawdzono demo, plan dnia, quiz z błędną odpowiedzią, fiszkę, odpowiedź otwartą, zapis przerwy, wznowienie oraz cele i ich ustawienia. Widoki mobilne oglądano przy 390 × 844 px.
- Uruchomiono cały istniejący zestaw: **129 testów, wszystkie przechodzą**. Pojawiają się ostrzeżenia `ResourceWarning` dotyczące zasobów testowych.
- Dodatkowe odtwarzalne scenariusze wykonano przez klienta testowego Flask na oddzielnych tymczasowych bazach. Wyniki: `output/student-audit-2026-10-15/scenarios.json`; skrypt: `output/student-audit-2026-10-15/scenarios.py`.
- Zrzuty: `output/student-audit-2026-10-15/today-mobile.png` i `goals-mobile.png`. Dane są demonstracyjne.
- Nie zmieniano kodu aplikacji, lokalnej bazy użytkownika ani produkcji. Rzeczywiste logowanie AI, jakość generowania, wydajność produkcji i pełny audyt dostępności pozostają niezweryfikowane w tej analizie.

## Czego potrzebuje student

Założenie robocze: kilka przedmiotów, terminy zaliczeń, materiały w różnych formatach, zmienna ilość czasu oraz nauka na laptopie i telefonie. Należy zweryfikować je z docelowymi użytkownikami.

| Potrzeba | Praktyczne oczekiwanie | Stan projektu |
|---|---|---|
| Szybko zacząć | Wrzucam materiał lub wklejam notatkę i od razu wiem, co zrobić | Upload jest prosty; przygotowanie z pliku wymaga AI, a sama notatka nie tworzy sesji |
| Zrozumieć | Krótkie wyjaśnienie, przykład, własna próba, powrót do źródła | Są notatki, podpowiedzi, wyjaśnienia i kryteria; przejście czytanie–ćwiczenie wymaga ręcznego przygotowania |
| Przygotować się do sesji | Jeden plan obejmuje kilka egzaminów i wspólny dostępny czas | Cele mają zakres i dni, ale domyślny plan wybiera jeden najbliższy niezakończony cel |
| Odkryć braki | Widzę niesprawdzone zagadnienia i błędy, a nie sam procent wykonania | Są trudności i tematy bez pytań; brak pokrycia wymagań egzaminu na poziomie zagadnień |
| Uczyć się w realnych warunkach | Mogę odpowiedzieć na kartce, przerwać pisanie, wrócić z telefonu | Zapisane wyniki i sesje są trwałe; bieżący szkic nie jest zachowany, odpowiedzi otwarte wymagają tekstu |
| Zachować porządek | Przenoszę materiał, poprawiam import i archiwizuję zaliczony semestr | Można archiwizować ćwiczenia; brak analogicznych operacji dla przedmiotów, tematów i notatek |
| Korzystać z materiałów kierunkowych | Schematy, fotografie, wykresy i odpowiedni format odpowiedzi | Matematyka, tabele i kod są; brak obrazków w samych notatkach i ćwiczeniach |

## Co już działa dobrze i warto zachować

1. **Kilka metod nauki w jednym temacie.** Fiszki, luki, quizy, pytania otwarte i zadania nie wymagają pięciu osobnych kolekcji materiałów.
2. **Historia i odporność zapisu ocen.** Migawki treści, ochrona przed podwójnym zapisem, cofnięcie ostatniej oceny i zachowanie starszych sesji są ważne dla zaufania.
3. **Domknięcie pracy po błędzie.** Jest przegląd własnych odpowiedzi, wzorzec, wyjaśnienie, kryteria oraz tryb trudności. Nie są już brakami opisanymi w historycznym audycie.
4. **Sprawdzian bez przedwczesnego ujawniania wzorców.** Automatyczna ocena quizów jest oddzielona od samooceny pozostałych odpowiedzi.
5. **Czytanie treści naukowych.** Markdown, wzory, tabele, kod i spis rozdziałów są dobrym fundamentem dla studiów.
6. **Spokojny, responsywny interfejs.** Oglądane ekrany przy 390 px są czytelne. Problemem jest bardziej liczba decyzji i długość drogi do zadania niż sama estetyka.
7. **Import wielu pytań i kolejne opracowanie rozdziału.** Te funkcje już są; potrzebują łatwiejszego dostępu i lepszego dopasowania do pracy z większym kursem.

## Potwierdzone problemy

### 1. Przerwa gubi rozpoczętą odpowiedź — P0

**Odtworzenie w przeglądarce:** rozpocząć pytanie otwarte, wpisać odpowiedź bez jej wysyłania, kliknąć „Zapisz przerwę i wróć później”, następnie wznowić sesję. Pole odpowiedzi jest puste.

Komunikat „Odpowiedzi i kolejność są zachowane” odnosi się do wysłanych odpowiedzi; student może odczytać go jako zachowanie także bieżącej pracy. Na zadaniu rachunkowym lub dłuższej odpowiedzi oznacza to realną stratę.

**Podstawa:** `madra/templates/study.html:12`, `madra/study.py:294`, `madra/study.py:485`, brak obsługi szkiców w `madra/static/app.js`. Wznowiona karta nie odtwarza tekstu szkicu.

**Zmiana:** zapisywać szkic i wybór quizu przed przerwą; zapewnić automatyczny zapis podczas pisania oraz przywrócenie po odświeżeniu. To osobny stan od wysłanej odpowiedzi i oceny. Podobnej ochrony potrzebuje edycja długiej notatki.

**Warunek ukończenia:** wpisany tekst wraca po przerwie i odświeżeniu, bez naliczenia próby i bez odsłonięcia wzorca.

### 2. Kilka egzaminów nie tworzy wspólnego planu — P0/P1

Domyślny plan oraz globalny start wybierają jeden najbliższy niezakończony cel. Drugi przedmiot nie dostaje automatycznie części czasu, choć jego egzamin może być niedługo później. Budżety celów są niezależne: dwa cele po 30 minut nie pytają, czy student ma łącznie 30 czy 60 minut.

Dodatkowo `nearest_goal()` nie odrzuca celów po terminie. Scenariusz z egzaminem wczoraj i kolejnym za cztery dni nadal wybiera pierwszy cel.

**Podstawa:** `madra/services/goals.py:163`, `madra/planning.py:65`, `madra/study.py:93`. Potwierdzone scenariuszami `multiple_exams` i `expired_goal`.

**Zmiana:** najpierw rozwiązać zaległy cel przez prostą decyzję „zakończ / zmień termin / pozostaw do samodzielnej nauki”; następnie wprowadzić wspólny budżet dnia i widoczny podział między aktywne egzaminy. Ręczne uruchomienie dowolnego przedmiotu nadal jest potrzebne.

**Warunek ukończenia:** dwa bliskie egzaminy pojawiają się w jednym planie; przeterminowany cel nie przejmuje domyślnego planu bez jawnej decyzji.

### 3. Licznik trudności i przycisk obejmują różne zakresy — P0

Na ekranie Dzisiaj liczba trudnych ćwiczeń jest globalna, a „Przećwicz trudności” dziedziczy zakres najbliższego celu. Jeśli jedyny błąd jest w innym przedmiocie, student widzi informację o trudnościach, po czym dostaje komunikat o braku ćwiczeń i wraca do biblioteki.

**Podstawa:** `madra/planning.py:65`, `madra/templates/today.html:90`, `madra/study.py:61`. Potwierdzone scenariuszem `global_difficulty_scope_mismatch`.

**Zmiana:** licznik i akcja muszą korzystać z tego samego zakresu. Pokazać nazwę zakresu przy przycisku oraz możliwość wyboru wszystkich przedmiotów.

**Warunek ukończenia:** kliknięcie obietnicy „1 trudne ćwiczenie” prowadzi do tego ćwiczenia albo do jawnego wyboru zakresu, bez pustej ścieżki.

### 4. Plan celu i szybki start mają różne budżety — P1

Cel przyjmuje dzienny czas 5–180 minut, ale Dzisiaj buduje propozycję na sztywno na 10 minut. Skrót „Ucz się do celu” również domyślnie wysyła 10. Wybór czasu w głównym formularzu nie aktualizuje widocznej propozycji dziesięciominutowej.

**Podstawa:** `madra/planning.py:68`, `madra/templates/macros.html:70`, `madra/templates/today.html:109`.

**Zmiana:** wspólny, widoczny czas sesji; domyślnie zgodny z planem dnia, z łatwą możliwością skrócenia. Plan tygodniowy i uruchamiana sesja powinny wyraźnie opisywać swój związek.

### 5. Biblioteka nie ma pełnego cyklu porządkowania — P1

Są tworzenie i edycja przedmiotów, tematów oraz notatek, ale brak ich przenoszenia, archiwizacji i usuwania w normalnym przebiegu. Archiwizacja i przywracanie obejmują ćwiczenia. Usunięcie pliku dotyczy niezapisanego szkicu; zapisany oryginał i opracowanie nie mają analogicznej operacji.

Student po omyłkowym dodaniu notatki, zmianie podziału tematów albo zakończeniu semestru nie ma wygodnego sposobu uprzątnięcia biblioteki. Lista wszystkich plików rośnie nad przedmiotami; wyszukiwanie nie filtruje tej listy.

**Podstawa:** `madra/library.py`, `madra/templates/library.html`, `madra/templates/topic.html`, `madra/uploads.py:285`. Sprawdzono komplet tras zarządzania.

**Zmiana:** archiwum przedmiotu/semestru, przenoszenie tematów i treści, kosz z przywracaniem, filtrowanie plików. Wspólne operacje na zaznaczonych elementach dopiero tam, gdzie skala materiału je uzasadnia.

## Braki i uproszczenia produktu

### Pierwsza wartościowa sesja wymaga zbyt dużo przygotowania — P1

Na pustym koncie podstawowa ręczna ścieżka to przedmiot → temat → materiał → ćwiczenie → sesja. Samo dodanie notatki nie pozwala rozpocząć sesji: potwierdzony scenariusz przekierowuje do biblioteki i nie tworzy sesji. Upload może skrócić organizację, ale notatka i pytania z pliku powstają dopiero po połączeniu AI.

Proponowany początek: „Wgraj materiały”, „Wklej notatkę”, „Dodaj gotowe pytania”. Strukturę przedmiotów i tematów można zaproponować po drodze. Z samej notatki można zaoferować prostą sesję czytania i samodzielnego odtwarzania treści bez udawania, że aplikacja automatycznie oceniła odpowiedź.

Przycisk „Utwórz pytanie do tej notatki” otwiera ogólny formularz w temacie, bez wstępnego ustawienia tej notatki jako źródła (`madra/templates/material.html:14`). Warto przenosić bieżącą notatkę, rozdział i zaznaczony fragment. Czytnik nie zapisuje stanu przeczytania rozdziałów ani osobnej ostatniej pozycji czytania; fragment URL pomaga tylko, gdy użytkownik zachowa konkretny link.

### Import nie obejmuje wszystkich materiałów z uczelni — P1 zależnie od grupy

Obsługiwane pliki to PDF, DOCX, TXT i MD, pojedynczo, do 10 MB i 100 stron PDF. To rozsądne ograniczenia pierwszej wersji, ale prezentacje PPTX, zdjęcia tablicy i większe skrypty wymagają konwersji lub ręcznego dzielenia. Nie ma wgrywania całego zestawu plików naraz. Import pytań obsługuje tekstowy eksport Anki, nie `.apkg`.

Najpierw wyraźnie podać sposób przygotowania nieobsługiwanego formatu i zachować dobry import PDF. Następny format wybrać po zebraniu prawdziwych materiałów studentów; PPTX i zdjęcia są kandydatami, a nie koniecznością wdrażania wszystkiego od razu.

### Schematy i zadania na kartce są ważniejsze niż kolejne typy tekstowych pytań — P1 zależnie od kierunku

PDF może zostać przeanalizowany wizualnie przez AI, lecz ćwiczenie nie potrafi zawierać własnego obrazka. Renderer wyłącza obrazy Markdown (`madra/services/formatting.py:10`). To ograniczenie dla anatomii, histologii, geometrii, obwodów i interpretacji wykresów. Rozpoznanie obrazka przez AI nie daje studentowi ćwiczenia z tym obrazkiem.

Dodać załącznik lub wycinek strony do pytania, potem ewentualnie zasłanianie fragmentów schematu. Dla zadań otwartych umożliwić „Rozwiązuję na kartce / odpowiadam ustnie”, następnie porównanie i samoocenę. Obecne wymaganie wpisania tekstu, choćby „nie wiem”, jest dodatkowym kosztem na telefonie.

### AI wymaga zbyt wiele wiedzy organizacyjnej — P1

Interfejs aplikacji wymaga połączenia ChatGPT i opisuje dostęp jako przeznaczony dla uprawnionych kont Plus/Pro; generowanie jest związane z jednym modelem. To opis warunków narzuconych przez bieżący kod, nie niezależna weryfikacja aktualnej oferty OpenAI. W wariancie domenowym istnieje ścieżka ręcznego wklejenia adresu po nieudanym powrocie z logowania. To trudne miejsce na ścieżce początkującego użytkownika.

Przed uploadem pokazać krótko warunek użycia AI i alternatywną ścieżkę ręczną. Po połączeniu wracać do konkretnego pliku. Użytkownika interesuje wynik, a nazwa modelu może pozostać w szczegółach połączenia.

Domyślny prompt prosi o obszerną notatkę 12–30 tys. znaków i 6–20 ćwiczeń. Dla powtórki przed zaliczeniem warto zaoferować „Szybka powtórka”, „Wyjaśnij od podstaw” i „Przygotuj zadania”, z sensownymi ustawieniami. Obszerne opracowanie nadal jest wartościowe dla pierwszej nauki.

Ekran generowania pokazuje etapy i pozwala wyjść, co jest dobre. Nie ma anulowania zadania; błędy miejscami pokazują techniczne kody. Warto dodać anulowanie, prosty komunikat i konkretną następną akcję. Nie oceniano realnego czasu ani niezawodności dostawcy.

### Liczba pytań nie pokazuje pokrycia egzaminu — P1

Opracowanie ma maksymalnie 20 ćwiczeń, nawet dla obszernego pliku. Kolejne opracowanie rozdziału już działa, ale wymaga powrotu do ekranu zapisanego pliku, przygotowania szkicu, generowania i ponownego zatwierdzenia.

Obecny cel wykrywa temat z zerem ćwiczeń. Temat z jednym pytaniem o definicję i wieloma nieprzećwiczonymi zagadnieniami nie jest już „tematem bez ćwiczeń”. Potrzebna jest prosta lista wymagań lub zagadnień egzaminu ze stanem „materiał jest / próba była / do powtórki / jeszcze niesprawdzone”. AI może zaproponować mapowanie, które student sprawdzi.

Nie zwiększać tylko limitu pytań. Dać możliwość uzupełnienia wybranego zagadnienia bez tworzenia za każdym razem kolejnej obszernej notatki i bez powtarzania podobnych pytań.

### „Zapamiętanie / Zrozumienie / Zastosowanie” brzmi mocniej, niż uzasadniają dane — P1

Wymiary wynikają z typu ćwiczenia: każdy quiz należy do zrozumienia, każde zadanie do zastosowania. Test syntetyczny z jednym quizem odtwarzającym fakt daje 100% „Zrozumienia”; kategorie bez pytań pokazują 0%.

Wyjaśnienie sposobu liczenia jest dostępne i trzeba je zachować, ale sam nagłówek i procent mogą sugerować diagnozę wiedzy. Użyteczniejsze są liczby: „z 12 zagadnień: 4 niesprawdzone, 3 z błędami, 5 rozwiązanych samodzielnie”, osobno wyniki po przerwie i próby z pomocą. Kategorie bez danych powinny pokazywać „Brak danych”.

Nie ma potrzeby zastępowania tego pozornie precyzyjnym wynikiem gotowości do egzaminu.

### Próbny sprawdzian potrzebuje własnych reguł — P1/P2

Obecnie jest to losowy zestaw dobrany do szacunkowego czasu. Student nie może normalnie pominąć pytania, oznaczyć go do powrotu, zmienić wcześniejszej odpowiedzi przed zakończeniem ani zobaczyć panelu wszystkich pytań. Czas jest szacunkiem zestawu, nie odmierzanym limitem egzaminu.

Dobór według minut może wykluczać dłuższe zadania: w syntetycznym banku zadanie 15-minutowe nie trafiło do żadnego z 20 sprawdzianów o budżecie 10 minut, gdy były krótsze pytania. Jest to zgodne z obecną regułą, ale taki zestaw nie jest automatycznie reprezentatywną próbą całego egzaminu.

Pozwolić określić liczbę pytań i rozkład tematów lub użyć własnego zestawu egzaminacyjnego. Dodać nawigację, zmianę odpowiedzi oraz opcjonalny zegar. Nie narzucać zegara w zwykłej nauce.

### Powrót po przerwie i regularność — P2

Krótka sesja ogranicza bieżącą porcję, ale nie tworzy planu odrobienia zaległości na kolejne dni. Powtórki korzystają z prostych odstępów; ocena „Jeszcze raz” ustawia jutro, a ponowną próbę tego samego dnia można uruchomić przez tryb trudności.

Dla chętnego użytkownika przyda się „wróć do tego po kilku innych pytaniach”, limit zaległości na dzień i plan powrotu rozłożony na tydzień. Przypomnienia powinny być opcjonalne i prowadzić do konkretnej sesji. Pełne offline można etapować: najpierw dostęp do pobranej notatki, później zapis odpowiedzi z synchronizacją.

### Dzielenie się i trwałość dostępu — P2, zależnie od sposobu publikacji

Studenci mogą chcieć wymienić zestaw z grupą. Dla tej potrzeby wystarczy początkowo eksport/import jednego tematu; nie trzeba od razu budować grup, ról i wspólnej edycji. Obecny eksport całego konta JSON/ZIP nie jest takim przebiegiem, a automatyczny import własnego archiwum nie jest zaimplementowany.

Odzyskiwanie hasła ma znaczenie dla publicznej usługi z wielomiesięcznymi materiałami. Dokumentacja świadomie pozostawia je poza bieżącym zakresem; ten audyt nie zmienia tej decyzji. Sam adres e-mail obecnie służy logowaniu i nie zapewnia odzyskania dostępu.

## Co uprościć lub schować

| Element | Koszt dla studenta | Proponowane uproszczenie |
|---|---|---|
| Kilka przycisków nauki i sprawdzianu na jednym ekranie | Trudno odgadnąć różnicę między szybkim startem i konfiguracją | Główne „Ucz się”, obok „Sprawdź się”; czas i zakres w jednym miejscu |
| „Połączenie AI” jako jedna z pięciu głównych zakładek telefonu | Ustawienie integracji zajmuje miejsce codziennej czynności | Status przy dodawaniu materiału i zarządzanie w ustawieniach konta |
| Ogólny motywacyjny nagłówek i duży panel startowy | Na telefonie konkretne zadania i terminy są niżej | Na pierwszym ekranie zakres, dostępny czas i następna akcja; krótszy tekst wstępny |
| Najpierw dodanie celu, później edycja zakresu i dni | Dwa formularze do jednego zamiaru | Jeden krótki formularz; dni i ważność opcjonalnie rozwijane |
| Ważność 1–3 ustawiana dla każdego tematu | Student musi sam pełnić rolę planisty | Domyślnie równa; priorytet ustawia tylko tam, gdzie jest potrzebny |
| Powód błędu i użycie pomocy przy każdej ocenie | Dodatkowe decyzje także po łatwym pytaniu | Zwinąć do „Dodaj adnotację”; podpowiedzi mogą automatycznie oznaczać użycie pomocy |
| Ręczne wpisanie numeru rozdziału | Wymaga pamiętania indeksów i znaczenia zera | Lista tytułów rozdziałów; „Cała notatka” jako normalna opcja |
| Poprawna opcja quizu wpisywana ponownie jako tekst | Literówka lub spacja powoduje błąd walidacji | Zaznaczenie poprawnej odpowiedzi przy jej wariancie |
| Import pokazujący nazwy JSON/CSV/TSV i pól | Początkujący musi rozumieć format danych | „Wklej pytania i odpowiedzi”, podgląd kolumn, prosty szablon; formaty w szczegółach |
| Dwukrotne potwierdzanie quizu | Dodatkowe kliknięcie na każdy element | Rozważyć zapis po sprawdzeniu i przycisk „Dalej”, z zachowaniem cofnięcia i czytelnego stanu zapisu |
| Kilka miejsc eksportu danych | Rzadkie działanie konkuruje z nauką | Jeden obszar „Moje dane” w koncie |
| „Plan nauki” nad listą rozdziałów | Może być mylony z harmonogramem dziennym i tygodniowym | „Rozdziały” lub „Kolejność czytania” |

Nie usuwałbym pięciu typów ćwiczeń, samooceny, źródeł, podpowiedzi ani historii. Należy podawać je w odpowiednim momencie. Najpierw ograniczyć widoczne ustawienia i powielone akcje, a następnie sprawdzić z użytkownikami, czy cztery poziomy samooceny wymagają dalszego uproszczenia.

## Czego nie rozbudowywać teraz

Rankingi, punkty, sklep, społecznościowy feed, publiczny marketplace, rozbudowane profile i automatyczne ocenianie każdej odpowiedzi przez AI nie rozwiązują wskazanych problemów. Pełny plan zajęć, zarządzanie całym życiem studenckim i rozbudowany Pomodoro również rozszerzałyby zakres produktu.

Nie traktować zaawansowanego algorytmu powtórek jako zamiennika zachowania szkiców, poprawnych zakresów i wygodnego przygotowania materiału. Warto go rozważyć później na podstawie historii realnej nauki.

## Proponowana kolejność zmian

| Etap | Zakres | Sprawdzalny rezultat |
|---|---|---|
| 1. Zaufanie do podstaw | Szkice odpowiedzi, zgodność licznika i zakresu, obsługa celów po terminie | Przerwa nie gubi pisania; akcja otwiera obiecany materiał; dawny egzamin nie przejmuje planu |
| 2. Szybszy start i porządek | Wklejenie materiału, prosta ścieżka do pierwszej sesji, archiwum i przenoszenie | Nowy użytkownik kończy pierwszą sesję bez pomocy; porządkuje materiał dodany w złe miejsce |
| 3. Przygotowanie do sesji egzaminacyjnej | Wspólny budżet kilku celów, lista zagadnień, spójny czas, lepszy sprawdzian | Plan mieści się w łącznym czasie; pokazuje, czego jeszcze nie sprawdzono |
| 4. Funkcje wybranego kierunku | Zdjęcia/schematy, odpowiedź na kartce, potrzebne formaty | Student rozwiązuje typowe zadanie z własnego kursu bez obchodzenia ograniczeń |
| 5. Regularność i wymiana | Plan powrotu, opcjonalne przypomnienia, etapowe offline, wymiana tematu | Możliwa krótka sesja w drodze i powrót po zaległościach; zestaw można przekazać bez eksportu całego konta |

Najpierw sprawdzić z 5–8 studentami różnych kierunków trzy zadania: przygotowanie nauki z własnego materiału, dwa egzaminy w jednym tygodniu i przerwanie odpowiedzi na telefonie. To propozycja małego badania jakościowego, nie próba reprezentatywna.

Mierzyć czas do pierwszej ukończonej sesji, miejsca wymagające wyjaśnienia, utratę szkiców, rozpoznanie niesprawdzonego zakresu i trafność wyboru kolejnego zadania. Osobno ocenić poprawność opracowań AI względem oryginału. Liczba kliknięć i liczba funkcji same nie świadczą o jakości nauki.

## Uzasadnienie zasad

Praktyka przypominania, rozłożenie pracy w czasie oraz łączenie rozwiązanych przykładów z samodzielną próbą mają oparcie w [przewodniku IES / What Works Clearinghouse](https://ies.ed.gov/ncee/wwc/PracticeGuide/1). Wspiera to zachowanie fundamentów nauki w projekcie; nie dowodzi skuteczności tej aplikacji.

Odkładanie rzadkich i zaawansowanych ustawień do momentu, gdy są potrzebne, opisuje [Nielsen Norman Group — Progressive Disclosure](https://www.nngroup.com/articles/progressive-disclosure/). Konkretna propozycja uproszczenia ekranów powyżej jest oceną tego projektu i wymaga sprawdzenia z jego użytkownikami.
