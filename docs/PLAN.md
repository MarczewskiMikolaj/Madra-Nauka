# Mądra Nauka 2.0 — plan produktu i realizacji

Data: 11 października 2026. Cel: wskrzesić projekt jako osobiste centrum nauki, w którym fiszki są jedną z metod pracy.

## 1. Cel produktu

Użytkownik organizuje materiał, ćwiczy na różne sposoby i otrzymuje plan kolejnej sesji. Główny przebieg: przedmiot → temat → materiały → ćwiczenia → cel → sesja → informacja zwrotna → powtórka.

Pierwszą grupą użytkowników są osoby samodzielnie przygotowujące się do sprawdzianów, egzaminów i rozwijające konkretne umiejętności. Projekt nie zakłada na starcie szkoły, marketplace ani platformy sprzedaży kursów.

Zasady:
- jeden temat może zawierać notatki, źródła i wiele metod ćwiczenia;
- treść, postęp użytkownika i historia odpowiedzi są oddzielone;
- sukces zapisu oznacza trwały zapis; ponowienie operacji nie tworzy duplikatu;
- aplikacja wyjaśnia, dlaczego dane ćwiczenie jest w planie;
- samoocena i obiektywny wynik quizu są jawnie odróżnione;
- statystyki opisują zarejestrowane ćwiczenia, nie obiecują zdania egzaminu;
- AI proponuje, a użytkownik może sprawdzić źródło i poprawić wynik.

## 2. Mapa produktu

| Moduł | Docelowy zakres |
|---|---|
| Dzisiaj | Kolejka zaległych ćwiczeń, nowe zagadnienia, wznowienie sesji, krótka sesja, cele |
| Biblioteka | Przedmioty, tematy, notatki, linki, pliki, tagi, wyszukiwanie, archiwum |
| Warsztat nauki | Fiszki, quizy, pytania otwarte, zadania, luki, wyjaśnienie własnymi słowami |
| Cele | Termin, zakres, dostępny czas, plan tygodniowy i aktualizacja po wynikach |
| Postępy | Zapamiętanie, zrozumienie, zastosowanie; aktywność i analiza błędów |
| Asystent | Ćwiczenia z materiału, wyjaśnienia, pytania uzupełniające, źródła |
| Konto | Logowanie, preferencje, eksport danych, przypomnienia, usunięcie konta |

## 3. MVP wykonywane w tym etapie

### Funkcje

1. Rejestracja i logowanie. Samodzielne, izolowane konto demonstracyjne z przykładowymi materiałami pozwala przetestować produkt bez rejestracji.
2. Tworzenie przedmiotów/przestrzeni nauki i tematów; opis i kolor przedmiotu.
3. Tworzenie i edycja materiałów tekstowych oraz linków. Linki tylko HTTP/HTTPS; materiały tekstowe bez wykonywania HTML.
4. Tworzenie i edycja pięciu typów ćwiczeń: fiszka, pytanie otwarte, quiz jednokrotnego wyboru, zadanie, luka. Odpowiedź wzorcowa, czas ćwiczenia i wymiar kompetencji.
5. Sesje mieszane, globalne lub dla przedmiotu/tematu. Limit czasu 5/10/20 minut, kolejność zaległe → nowe → pozostałe; możliwość skończenia wcześniej i wznowienia.
6. Quiz oceniany na serwerze. Pozostałe odpowiedzi porównywane przez użytkownika ze wzorcem i oceniane w czterech stopniach. Pytanie otwarte i zadanie wymagają próby odpowiedzi przed pokazaniem wzorca.
7. Trwała historia pojedynczych odpowiedzi. Zapis transakcyjny i idempotentny. Korekta ostatniej oceny odtwarza poprzedni stan postępu.
8. Cele dla przedmiotu, termin i dzienny budżet minut. Pokrycie ćwiczeń, pozostałe dni i wskazówka planowania bez predykcji zdawalności.
9. Statystyki aktywności, rzeczywistej liczby odpowiedzi, samooceny i trzech wymiarów kompetencji.
10. Eksport danych własnego konta do JSON. Import starych zestawów i użytkowników przez jawne polecenie CLI z trybem podglądu, bez zmiany plików źródłowych. Zaszyfrowani użytkownicy wymagają starego klucza Fernet.
11. Responsywny interfejs po polsku, dostępne formularze, widoczny fokus, wspólne komponenty, czytelne stany puste i błędy.

### Rozszerzenie wdrożone: materiały z plików

Wgrywanie PDF (także skanów), DOCX, TXT i Markdown. Oryginał jest przekazywany bezpośrednio do AI przez plan ChatGPT; nie ma lokalnej ekstrakcji tekstu ani generowania ćwiczeń z fragmentów. AI tworzy notatkę, objaśnienia, przykłady i ćwiczenia pięciu typów. PDF zachowuje układ i ilustracje, DOCX jest analizowany tekstowo. Użytkownik sprawdza wynik i wskazania źródeł przed zapisem. Pełny kalendarz nauki nadal wymaga kolejnego etapu.

### Poza pierwszym MVP

Audio, pełne offline, Web Push, współdzielenie i grupy, FSRS, odzyskiwanie hasła przez e-mail. Te funkcje mają osobne etapy i nie będą imitowane nieaktywnymi przyciskami.

### Kryterium ukończenia MVP

Nowy użytkownik potrafi utworzyć przedmiot, temat, notatkę, pytanie otwarte i zadanie, ustawić cel, wykonać mieszaną sesję i zobaczyć zapisany postęp po ponownym uruchomieniu. Inny użytkownik nie widzi jego danych. Podwójne wysłanie tej samej oceny nie zwiększa statystyk. Quiz sprawdza odpowiedź na serwerze. Poprawa treści ćwiczenia zachowuje jego historię. Interfejs działa na telefonie i desktopie.

## 4. Architektura MVP

Zachowujemy Python i Flask, przebudowujemy strukturę wokół domeny:

```text
app.py                    punkt uruchomienia
madra/
  __init__.py             fabryka aplikacji i konfiguracja
  db.py                   połączenia, transakcje, migracje
  auth.py                 konta, autoryzacja, CSRF
  library.py              przedmioty, tematy, materiały, ćwiczenia
  study.py                sesje i odpowiedzi
  planning.py             cele i statystyki
  services/               harmonogram, planowanie, demo, import
  migrations/             wersjonowany schemat SQL
  templates/              wspólny layout i ekrany
  static/                 CSS, JS i ikony
tests/                    integracyjne testy zachowania
docs/                     plan i decyzje
instance/                 lokalne dane ignorowane przez Git
```

SQLite w MVP daje transakcje i prosty lokalny start bez usług zewnętrznych. Produkcyjny etap wieloinstancyjny wymaga PostgreSQL. SQLite potrzebuje trwałego dysku i pojedynczej instancji; nie wdrażamy tej konfiguracji do efemerycznego Cloud Run. Dotychczasowe pliki JSON nie są automatycznie zapisywane ani zastępowane.

Sesja przeglądarki zawiera tylko identyfikator konta i token CSRF. Ćwiczenia oraz odpowiedzi pozostają w bazie. Sesja nauki zachowuje migawkę treści i kolejność, więc edycja materiału nie zmienia trwającej sesji.

## 5. Model danych

| Encja | Najważniejsze pola |
|---|---|
| User | ID, login, hash hasła, tryb demo, data utworzenia |
| Workspace | ID, właściciel, nazwa, opis, kolor |
| Topic | ID, przedmiot, nazwa, opis |
| Material | ID, temat, typ note/link, tytuł, treść/URL |
| Activity | ID, temat, typ, pytanie, wzorzec, warianty quizu, wymiar, szacowany czas |
| ActivityProgress | użytkownik, ćwiczenie, licznik, interwał, termin, ostatnia ocena |
| StudySession | ID, użytkownik, status, budżet czasu, data |
| SessionItem | kolejność, ćwiczenie, migawka treści, próba odpowiedzi |
| ReviewEvent | ID, pozycja sesji, ocena, odpowiedź, poprzedni stan postępu, czas |
| Goal | ID, właściciel, przedmiot, tytuł, termin, dzienny budżet |

Współdzielenie później doda Membership i rozdzieli właściciela treści od uprawnienia do jej użycia. Historia odpowiedzi stanowi podstawę późniejszego harmonogramu FSRS.

## 6. Harmonogram i metryki

MVP stosuje jawne proste odstępy zależne od poprzedniego interwału i oceny. Błąd wraca do nauki następnego dnia, trudna odpowiedź skraca odstęp, poprawna go wydłuża. Użytkownik może ćwiczyć też poza terminem. To nie jest FSRS ani model pamięci.

Wymiary: zapamiętanie (fiszki/luki), zrozumienie (otwarte/quizy), zastosowanie (zadania). Widok postępu agreguje ostatnie oceny ćwiczeń i pokazuje zakres danych. Czas planu jest szacunkiem; faktyczna aktywność liczona jest z odpowiedzi i sesji.

Docelowo mierzymy: ukończenie pierwszego przebiegu, powroty po 7 dniach, rozpoczęte i zakończone sesje, zaległości, skuteczność po przerwie, utratę/duplikację wyników. Prywatne treści nie trafiają do analityki produktowej.

## 7. Etapy po MVP

| Etap | Rezultat | Warunek zakończenia |
|---|---|---|
| A. Walidacja MVP | Testy z rzeczywistymi użytkownikami i poprawa przebiegu | Użytkownik samodzielnie kończy pierwszy przebieg; znane trudności mają poprawki |
| B. Produkcyjny fundament | PostgreSQL, migracje, staging, kopie, monitoring, limity prób logowania, odzyskanie konta | Odtworzenie backupu i test migracji; mierzalne błędy zapisu |
| C. Pełniejsza biblioteka | PDF, tagi, archiwizacja, wyszukiwanie, import CSV z podglądem | Źródła połączone z ćwiczeniami; bezpieczne uploady i limity |
| D. Plan egzaminu | Zakres tematów, dostępność, plan tygodniowy, próbny egzamin | Plan pokazuje wykonalność i przelicza zaległości |
| E. Asystent materiałów | Generowanie ćwiczeń i wyjaśnień ze źródłami | Użytkownik zatwierdza treść; koszty i limity jawne; ewaluacja błędów |
| F. Lepsza diagnoza | Przyczyny błędów, wyjaśnianie własnymi słowami, zależności pojęć | Zalecana metoda wynika z wyniku i przyczyny błędu |
| G. Offline i przypomnienia | IndexedDB, kolejka operacji, konflikty, ustawienia czasu | Utrata sieci/ponowienie nie gubią i nie dublują odpowiedzi |
| H. Współpraca | Udostępnianie, uprawnienia, własny postęp, wersje materiału | Cofnięcie dostępu skuteczne; brak przecieku między kontami |
| I. Personalizacja | Integracja FSRS, adaptacyjne sesje, plan po przerwie | Porównanie harmonogramów na historii; kontrolowana migracja terminów |

Kolejność dalszych etapów może zmienić się po walidacji. W pierwszej kolejności finansujemy niezawodność, użyteczność i materiały; płatne AI pojawia się po ustaleniu kosztów na aktywnego użytkownika.

## 8. Plan migracji starego projektu

1. Wykonać kopię starego repo i danych produkcyjnych przed przyszłym wdrożeniem.
2. Uruchomić nową aplikację z osobną bazą. Nie podmieniać produkcji podczas lokalnej pracy.
3. Uruchomić podgląd importu: liczniki kont, zestawów, kart, błędów i braków.
4. Jawnie zaimportować użytkowników z dawnymi hashami oraz zestawy jako przedmioty z tematem i fiszkami.
5. Zachować dawne statystyki w metadanych importu. Agregaty nie stają się wymyślonymi pojedynczymi zdarzeniami; dotychczasowe dane źródłowe pozostają do audytu.
6. Sprawdzić ponowienie importu, właścicieli, liczby obiektów i logowanie.
7. Dopiero po testach staging wybrać termin wdrożenia, wykonać ostatni import i przełączenie. Plan cofnięcia: powrót starej aplikacji i jej kopii danych.

## 9. Interfejs i jakość

Kierunek: jasne biurko do nauki, atramentowy tekst, niebieski akcent, zielony dla postępu. Czytelna nawigacja „Dzisiaj / Biblioteka / Cele / Postępy”. Plan dnia ma formę listy zadań; materiały i ćwiczenia własne typy widoków. Jedna dominująca akcja na ekran.

Weryfikacja:
- testy backendu: konta, CSRF, uprawnienia, walidacja, tworzenie treści, migawki, idempotencja, korekta, terminy, eksport i import;
- rzeczywista przeglądarka: demo, tworzenie tematu i treści, sesja, cel, statystyki, ekran mobilny;
- brak błędów JS i poziomego przewijania przy wąskim ekranie;
- dokumentacja uruchomienia od pustego środowiska i jawne ograniczenia deploymentu.

## 10. Ryzyka i decyzje do przyszłej produkcji

- Samoocena nie mierzy obiektywnie umiejętności; pokazujemy jej pochodzenie i rozbudujemy diagnozę.
- SQLite lokalnie, PostgreSQL dla skalowania. Hosting wybieramy razem z budżetem i wymaganiami trwałości.
- Import starego users.json wymaga posiadania właściwego klucza; nie odgadujemy go i nie nadpisujemy danych.
- AI może produkować błędne materiały; wymagane źródło, zatwierdzenie, limity i ewaluacja.
- Offline i współdzielenie wymagają jawnego wersjonowania i konfliktów; to odrębne etapy.
- MVP ma działać samodzielnie; integracje z dostawcami AI, pocztą i storage nie są warunkiem lokalnego startu.
