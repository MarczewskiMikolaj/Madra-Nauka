# Audyt aplikacji z perspektywy studenta

13 października 2026. Ocena wersji przed rozbudową przebiegu nauki.

Aktualizacja: opisane poniżej braki z ostatniej listy wdrożenia zostały zaadresowane w [planie i realizacji rozbudowy](STUDENT_IMPLEMENTATION_PLAN.md). Scenariusze i wyniki poniżej pozostają historycznym punktem odniesienia.

## Wniosek

Aplikacja daje podstawy samodzielnej pracy: porządkowanie materiałów, czytanie notatek, pięć rodzajów ćwiczeń, zapis odpowiedzi i powtórki. Najważniejszy brak to domknięcie procesu: rozpoznać problem → zrozumieć błąd → spróbować ponownie → sprawdzić wiedzę po przerwie. Obecny przebieg kończy się głównie licznikiem wykonanych odpowiedzi.

To symulacja użytkowania i audyt produktu, nie badanie z rzeczywistymi studentami ani ewaluacja jakości rzeczywistych odpowiedzi AI. Sprawdzono szablony, logikę planowania oraz pełne żądania aplikacji na syntetycznym koncie i osobnej bazie tymczasowej. Nie zmieniano kodu aplikacji ani danych produkcji w ramach tego audytu. Wyniki scenariuszy: `output/student-audit/scenarios.json`.

## Rola i zadanie

„Mam egzamin ze statystyki za siedem dni. Osiem tematów, notatki z wykładów i pół godziny dziennie. Prawdopodobieństwo warunkowe sprawia mi trudność. Chcę wiedzieć, co robić dzisiaj i czy potrafię samodzielnie rozwiązać zadanie.”

### 1. Zbieram materiał

Przedmioty, tematy, własne notatki, linki i pliki działają. Czytnik ma rozdziały. Jednak po dodaniu samej notatki start nauki przekierowuje do biblioteki z prośbą o utworzenie ćwiczeń. Student musi sam zbudować pytania albo połączyć AI. Brakuje krótkiego przebiegu „przeczytaj fragment → odpowiedz własnymi słowami → porównaj”, bez konieczności wcześniejszego przygotowania całego banku.

Dla większego kursu potrzebne będzie hurtowe dodawanie pytań i dodatkowe ćwiczenia do wybranego rozdziału. AI ma limit 20 ćwiczeń na opracowanie pliku; liczba podjętych ćwiczeń nie świadczy o pokryciu treści dużego skryptu. To ograniczenie produktu, nie dowód błędu konkretnego opracowania.

### 2. Ustalam zakres egzaminu

Cel obejmuje przedmiot, termin i dzienny czas. Nie określa tematów w zakresie egzaminu, ich znaczenia, wymagań ani dni dostępnych na naukę. Dzienne sesje wybierają ćwiczenia według terminów powtórek i czasu; nie korzystają z daty egzaminu ani zakresu celu.

Potwierdzony scenariusz: osiem tematów, jedno ćwiczenie. Błędna odpowiedź w quizie daje 100% pokrycia ćwiczeń, 0 minut pozostałego pierwszego przejścia i siedem zer w rozpisce tygodnia. „Pokrycie” jest opisane jako podjęcie ćwiczeń, więc nie jest to błąd samego wzoru procentu. Problemem jest jego mała przydatność do planowania przygotowania i brak widocznego zakresu, którego w ogóle nie sprawdzono.

### 3. Próbuję rozwiązać zadanie

Pytania otwarte i zadania wymagają własnej próby przed odkryciem odpowiedzi. To dobry fundament. Brakuje podpowiedzi stopniowanych i kryteriów samooceny: student może nie wiedzieć, czy odpowiedź jest częściowo poprawna i czego w niej zabrakło.

W quizie aplikacja pokazuje poprawną opcję. Autor może umieścić objaśnienia w materiałach, ale nie ma osobnego pola wyjaśniającego błąd ani połączenia „wróć do konkretnego fragmentu źródła” w sesji. Migawka sesji nie przenosi identyfikatora pliku ani lokalizacji źródła.

### 4. Popełniam błąd

Potwierdzony scenariusz: błędny quiz zapisuje ocenę 0 i termin jutro. Jeszcze tego samego dnia ćwiczenie ma stan `scheduled`. Nie ma osobnej akcji ćwiczenia trudności ani ponowienia błędnych odpowiedzi po kilku innych zadaniach. Dodatkowe utrwalenie może je ponownie wybrać, jeśli nie ma zaległych ani nowych ćwiczeń, lecz student nie kontroluje tego wyboru.

Podsumowanie zapisanej sesji pokazuje liczby, ale nie pytanie, własną odpowiedź, wzorzec ani wyjaśnienie. Ponowne otwarcie zakończonej sesji nadal pokazuje to podsumowanie. Brakuje przeglądu błędów i historii odpowiedzi dostępnej do czytania w interfejsie.

### 5. Zmieniam temat albo wracam po przerwie

Wznawianie istniejącej sesji jest niezawodne. Jednak rozpoczęcie sesji z innego tematu zwraca tę samą aktywną sesję bez wyjaśnienia. Potwierdzono to dwoma różnymi tematami. Potrzebna jest jawna decyzja: kontynuować poprzednią, zapisać przerwę i przejść do wybranego zakresu, albo ją zakończyć.

Po kilku dniach zaległości nie ma dedykowanego spokojnego planu powrotu: wyboru najważniejszych tematów i rozłożenia zaległych powtórek w dostępnym czasie.

### 6. Sprawdzam się przed egzaminem

Brakuje trybu sprawdzianu z odpowiedziami i informacją zwrotną dopiero na końcu, wyborem zakresu oraz analizą wyniku według tematów. Obecna sesja uczy z natychmiastowym odkrywaniem wzorca. Nie sprawdza osobno samodzielnego rozwiązania całego zestawu bez pomocy.

Wyniki samooceny i automatycznie sprawdzonych quizów są rozróżnione w opisie. Nie należy zmieniać ich w deklarację „gotowości do zdania”. Użyteczniejsze będą konkretne dane: czego nie sprawdzono, gdzie popełniam błędy i co potrafię po kilku dniach.

## Kolejność prac

| Priorytet | Funkcja | Warunek ukończenia |
|---|---|---|
| P0 | Przegląd odpowiedzi i błędów po sesji | Każde ocenione pytanie pokazuje własną odpowiedź, wzorzec i wynik; można wrócić do tej historii później. |
| P0 | „Przećwicz trudności” | Dostępny dla przedmiotu i tematu; wybiera ćwiczenia z ostatnią oceną 0–1. Dodatkowa praktyka ma jawne zasady zapisu postępu i powtórek. |
| P0 | Uczciwa informacja o zakresie i trudnościach w celu | Podjęte, trudne i niepodjęte ćwiczenia są oddzielone. Tematy bez pytań nie sugerują sprawdzonej wiedzy. Błędna próba nie daje pustego zalecenia nauki. |
| P0 | Jawna zmiana aktywnej sesji | Kliknięcie nauki w innym temacie wyjaśnia konflikt i pozwala świadomie wybrać dalszy przebieg. |
| P1 | Pomoc w zrozumieniu błędu | Wyjaśnienie odpowiedzi, opcjonalne podpowiedzi, kryteria samooceny i powrót do odpowiedniego źródła. Może działać na treściach autora bez wymagania AI. |
| P1 | Cel z zakresem i plan działania | Wybór tematów, dni nauki i ważności; sesja rzeczywiście korzysta z tych ustawień oraz uwzględnia trudności i powtórki. |
| P1 | Tryb próbnego sprawdzianu | Określony zakres, brak wzorców w czasie testu, podsumowanie według tematów; wyniki quizów i samooceny pozostają oddzielone. |
| P1 | Sprawne tworzenie banku ćwiczeń | Wklejenie/import wielu pytań z podglądem albo kolejne opracowanie wybranego rozdziału, bez ponownego wgrywania całego pliku. |
| P1/P2 | Czytelna treść naukowa | Bezpieczne formatowanie notatek, wzory matematyczne, tabele i kod. Obecne treści są renderowane jako tekst; potrzebność zależy od studiowanego przedmiotu. |
| P2 | Powrót po zaległościach, wybór metod i dostęp offline | Student może ograniczyć zakres sesji, dobrać rodzaj ćwiczeń i wrócić do nauki po przerwie; offline wymaga osobnego rozwiązania synchronizacji. |

## Czego nie trzeba dodawać teraz

Poczta, weryfikacja e-maila i odzyskiwanie konta pozostają poza zakresem zgodnie z decyzją użytkownika. Rankingi, punkty, sklep, rozbudowana grywalizacja i współdzielenie nie rozwiązują obecnych najważniejszych trudności. Automatyczne ocenianie wszystkich odpowiedzi przez AI nie jest warunkiem użytecznej pierwszej wersji — czytelne kryteria i dobra odpowiedź wzorcowa mają mniejszy koszt i są bardziej kontrolowalne.

Nie trzeba wdrożyć całej tabeli przed pierwszym wydaniem. Cztery P0 tworzą spójny następny etap. Potem warto sprawdzić go z kilkoma studentami różnych kierunków, na ich rzeczywistych materiałach, obserwując samodzielne ukończenie przebiegu i odnalezienie własnych trudności.

## Podstawa rekomendacji

Dobór funkcji jest oceną produktu na podstawie powyższych scenariuszy. Ogólne uzasadnienie dydaktyczne: praktyka przypominania, rozłożenie nauki w czasie, łączenie rozwiązanych przykładów z samodzielnymi zadaniami oraz pytania wymagające wyjaśniania są opisane w [przewodniku IES / What Works Clearinghouse](https://ies.ed.gov/ncee/wwc/PracticeGuide/1). Źródło wspiera te zasady; nie dowodzi skuteczności tej konkretnej aplikacji ani nie określa automatycznie priorytetów jej funkcji.
