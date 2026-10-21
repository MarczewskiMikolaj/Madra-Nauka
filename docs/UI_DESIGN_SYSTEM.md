# Spójny interfejs Mądrej Nauki

Kierunek: uporządkowane biurko do nauki. Treść i rozpoczęcie pracy mają pierwszeństwo przed ustawieniami. Istniejąca identyfikacja pozostaje rozpoznawalna.

## Tokeny

- Tło: `#f5f6fa`; powierzchnia: `#ffffff`; tekst: `#202a40`.
- Tekst pomocniczy: `#5e6b82`; linie: `#dde2ec`; akcent: `#3448cf`.
- Avenir Next / Segoe UI / systemowy sans-serif. Nagłówek 32 px, tytuł sekcji 20 px, tekst 15 px, etykiety i przyciski 14 px.
- Odstępy 8 / 16 / 24 / 32 px. Kontrolki 44 px; promień kontrolek 8 px, powierzchni 12 px.
- Primary: rozpoczęcie lub zapis. Secondary: dodatkowa akcja. Quiet: opcje i czynności pomocnicze. Kolory oceny odpowiedzi zachowują znaczenie.

## Układ

Nauka: jedna wyróżniona powierzchnia pracy, a pod nią wspólna lista rozwijanych narzędzi. Nie trzy oddzielne kafelki ustawień.

```
Nagłówek strony
┌ Dzisiejsza sesja ───────────────────┐
│ Krótki opis      czas + Rozpocznij   │
│ Podgląd zestawu / dodatkowe tryby    │
└────────────────────────────────────┘
┌ Plan tygodnia                      ┐
│ Cele i terminy                     │
│ Historia i postępy                 │
└────────────────────────────────────┘
```

Materiały: wyszukiwanie i dodawanie na jednym pasku, nagłówki przedmiotów oraz wiersze tematów na wspólnej osi. Wszystkie opcje przedmiotu w jednym menu. Temat: akcje w nagłówku, dwie zakładki i spójne wiersze ćwiczeń.

Przegląd kierunku: zamiast nowej palety, dekoracji i kolejnych kart zmieniamy hierarchię istniejących elementów. Akcent służy działaniu, a biała powierzchnia wyznacza obszar pracy. Kontrolki nie zmniejszają się w nagłówkach ani na telefonie. Reguły wspólne są w `madra/static/ui.css`; wcześniejszy arkusz zachowuje układy specjalistycznych ekranów.

## Pozostałe widoki

Wspólna klasa `app-ui` obejmuje również landing, logowanie i rejestrację. Każdy pełny szablon wskazuje `ui_view`; kontener `view-content` pozwala dopasować układ bez rozjeżdżania wspólnych kontrolek.

- Formularze przedmiotu, tematu, materiału, ćwiczenia, notatki i celu: szerokość 760 px, etykieta przy polu, osobny pasek działań. Podpowiedzi ćwiczenia znajdują się poza paskiem zapisu.
- Konto, połączenie AI i wysyłanie pliku: wyrównane kolumny, wspólne powierzchnie; jedna kolumna na mniejszych ekranach.
- Importy ćwiczeń i zestawów, podgląd opracowania: odstępy między elementami, przewijane bloki kodu, uporządkowany zapis.
- Czytanie i odtwarzanie notatki: czytelna szerokość tekstu, jednolite rozdziały i działania; czytnik wewnątrz edytora nie dodaje kolejnych obramowanych kart.
- Przygotowanie nauki, ćwiczenie, sprawdzian, przerwa, konflikt sesji i zakończenie: wspólne pola i przyciski; semantyczne kolory ocen pozostają zachowane.
- Podsumowanie: wyrównanie do lewej, trzy statystyki na jednej osi, lista odpowiedzi i przewijana tabela.
- Archiwum, błędy i statusy AI: ten sam system powierzchni, komunikatów i działań.

## Weryfikacja

185 testów funkcjonalnych przeszło. Wszystkie szablony Jinja kompilują się. Podglądy z testowych, tymczasowych baz obejmują wszystkie 29 pełnych szablonów widoków, z dodatkowymi wariantami formularzy i logowania: 34 strony. Pomiar DOM dla każdej strony przy 390 i 1280 px (68 pomiarów) nie wykazał poziomego przepełnienia. Podglądy mają wyłączone skrypty i odświeżanie; ta kontrola dotyczy układu, a zachowanie sprawdzają testy aplikacji.

Wizualnie sprawdzono m.in. konto, rejestrację, formularz ćwiczenia, podgląd opracowania, czytnik, sprawdzian i podsumowanie. Dane użytkownika nie były używane do przygotowania podglądów. Wyniki pomiarów: `output/playwright/ui-layout-report.json`.

## Korekta układów działań w Materiałach

Kontrola żywej aplikacji ujawniła menu „Rozbuduj zestaw” wychodzące poza lewą krawędź telefonu. Pomiar samego `scrollWidth` nie wykrywał tego błędu. Menu na końcu paska jest teraz wyrównane do prawej, a narzędzia sekcji na telefonie zajmują własny pełny rząd.

Materiały mają stały układ wyszukiwania i działań; pliki nie rozdzielają nagłówka od wyszukiwania. Temat i notatka używają `page-actions`, a przenoszenie osobnego `move-form`. Pasek zapisu importu na telefonie pozostaje nad dolną nawigacją.

Sprawdzono 8 adresów/stadiów widoku z aktywnym JavaScriptem przy 390, 768 i 1280 px. 48 kontroli przycisków i otwartych menu nie wykazało wyjścia poza lewą/prawą krawędź ani przycisków niższych niż 44 px. Raport: `output/playwright/materials-actions-audit.json`. 185 testów funkcjonalnych przeszło.

## Przebudowa ćwiczeń i notatek

Ćwiczenia korzystają z indeksu pytań i osobnego panelu wybranego pytania zamiast stosu rozwijanych kart. Wyszukiwanie, przyciski rodzaju i filtr statusu zawężają indeks. Na telefonie wybrane pytanie zastępuje indeks, a przycisk powrotu przywraca listę. Długie nazwy plików zawijają się w menu. W quizie radio, litera i tekst mają wspólną pionową oś środka; porównanie własnej i wzorcowej odpowiedzi ma dwie kolumny na komputerze.

Zakładka notatek jest spisem dokumentów: tytuł prowadzi do czytnika, fragment tekstu ma najwyżej 160 znaków, edycja jest akcją pomocniczą. Oryginalne pliki znajdują się w osobnej rozwijanej sekcji. Czytnik ma boczny spis rozdziałów, pojedynczą powierzchnię tekstu i działania pod treścią. Na mniejszych ekranach spis jest nad tekstem. Przejścia poprzedni/następny rozdział zachowują zapisywanie miejsca czytania.

Nowe szablony potwierdzono na działającym serwerze 8080. Na osobnej bazie testowej sprawdzono notatkę z trzema rozdziałami, przejście do kolejnego rozdziału i odtworzenie pozycji po ponownym wejściu bez fragmentu URL. Wizualna kontrola obejmuje komputer i telefon (390 px), a ćwiczenia także wybór pytania i powrót do indeksu. 185 testów aplikacji przeszło. Lokalny `app.py` jawnie włącza `TEMPLATES_AUTO_RELOAD`, żeby odświeżenie strony wczytywało aktualne szablony przy wyłączonym debuggerze.
