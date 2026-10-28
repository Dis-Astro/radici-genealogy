# Radici Genealogy

Radici è un'applicazione genealogica italiana pensata per chi ha poca esperienza con il computer: albero visivo, controlli grandi, compilazione guidata e stampe per album. Funziona localmente e usa il motore ufficiale **Gramps 6.0.8** tramite le sue API. È un progetto indipendente, non una release ufficiale Gramps.

**Stato:** anteprima Windows 5.0.0. Il progetto è nuovo. La candidatura per la firma gratuita è stata inviata a SignPath Foundation il 28 ottobre 2026 e il sito ha confermato la ricezione. È in attesa di valutazione: nessuna approvazione o firma è dichiarata. Gli eseguibili di anteprima sono non firmati. Non eludere avvisi o protezioni del computer.

## Funzioni

- Persone, famiglie, unioni multiple, persone senza legami e correzione delle parentele; undo delle operazioni supportate.
- Trascinamento delle schede, posizioni bloccabili, layout orizzontale/verticale, colori di famiglia e raccordi con indicazione degli incroci.
- Schede di dimensioni uniformi, nomi completi e font configurabili.
- A4, A3 e misure esplicite mm/cm; stampa SVG/PDF e album multipagina 150 × 100 mm con rimandi fra famiglie.
- Database nativo Gramps, import/export XML, foto e backup locali separati dal programma. Nessuna query SQL arbitraria.
- Finestra Windows con Microsoft WebView2 e servizio privato sul loopback; nessun account cloud richiesto per usare l'app.

## Windows

Richiede Windows 10/11 x64 e .NET Framework 4.6.2 o successivo. Il pacchetto include il runtime ufficiale Gramps e il componente Microsoft WebView2, con le rispettive licenze.

Le versioni pubblicate e lo stato della firma sono nella [pagina download](DOWNLOADS.md). La compilazione verificabile è in [BUILDING.md](BUILDING.md); i controlli automatici sono nella scheda [Actions](https://github.com/Dis-Astro/radici-genealogy/actions).

I dati sono in `%LOCALAPPDATA%\Radici\Archivio`; il programma in `%LOCALAPPDATA%\Programs\Radici`. L'installazione può importare una copia verificata da una chiavetta chiusa e non sostituisce un archivio locale esistente. La disinstallazione conserva i dati. Dettagli in [installazione desktop](docs/INSTALLAZIONE-DESKTOP.md).

## Docker e sviluppo

```sh
python scripts/init.py
docker compose up --build -d
```

Aprire `http://127.0.0.1:8787` con la password scelta. I volumi `genealogy`, `media` e `backups` sono distinti e persistenti. La porta è pubblicata sul solo loopback. Non usare `docker compose down -v` se si vogliono conservare i volumi. Il Dockerfile scarica il sorgente completo del tag ufficiale Gramps e ne verifica SHA-256.

```sh
docker compose --profile test run --rm test
```

La demo `python scripts/demo.py` usa solo persone inventate e dati in `runtime/`, escluso dal repository; non sostituisce un archivio Gramps. Password demo: `radici-demo-2026`.

## Limiti e verifica

La suite testa il vero motore genealogico, transazioni, import/export, backup, layout, stampa e accesso HTTP. La finestra desktop deve ancora essere collaudata su più PC, incluso hardware poco potente; non viene dichiarata una certificazione di accessibilità. Il layout migliora la leggibilità ma non garantisce l'assenza di ogni incrocio. Un albero numeroso non può avere tutti i nomi grandi su un unico foglio 150 × 100 mm: l'album divide i dettagli in più pagine.

L'editor non copre tutte le funzioni del desktop Gramps: ad esempio gli eventi complessi, fonti e note hanno editor limitati. Gli oggetti importati non mostrati dalla UI vengono conservati dal motore. Verificare esportazioni e backup su copie prima di migrare un archivio importante.

## Code signing policy

[Code signing policy](CODE_SIGNING_POLICY.md): candidatura a **SignPath Foundation** inviata il 28 ottobre 2026, in attesa di valutazione. L'eventuale firma sarà abilitata soltanto dopo approvazione, integrazione del build verificato e autorizzazione del responsabile del rilascio.

## Licenze, privacy e contributi

Applicazione e adattatore: [GPL-2.0-or-later](LICENSE); host e installatore Windows: [MIT](desktop/LICENSE-MIT.txt); font: SIL OFL. Gramps e le altre dipendenze mantengono le proprie licenze. Microsoft WebView2 mantiene i termini Microsoft: la sua ammissibilità al programma SignPath deve essere verificata con la Foundation. Vedi [NOTICE](NOTICE), [dipendenze](dependencies/README.md), [privacy](PRIVACY.md) e [contributi](CONTRIBUTING.md).

Il repository contiene soltanto codice e fixture di test sintetiche. Database, alberi, foto, esportazioni e credenziali degli utenti non devono essere caricati nelle issue o nei contributi.
