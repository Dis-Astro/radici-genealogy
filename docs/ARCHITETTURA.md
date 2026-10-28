# Scelte architetturali

## Base verificata

Scaricato archivio ufficiale `v6.0.8`, verificati `gramps/version.py` (6,0,8), `COPYING`, API database, oggetti genealogici, plugin XML e backend SQLite. Sorgente completo distribuito in `vendor/gramps-v6.0.8.zip`, hash in Dockerfile e NOTICE. Non è necessario decompilare o eseguire l’installer Windows.

Gramps divide modello (`gramps/gen/lib`: Person, Family, ChildRef, Event e altri oggetti), API/transaction/undo (`gramps/gen/db`), backend (`plugins/db/dbapi`) e GUI GTK (`gramps/gui`). I plugin ufficiali leggono/scrivono l’archivio XML completo. La nostra UI non ricostruisce le fonti o gli oggetti non visualizzati e non scrive SQL nel database Gramps.

File esaminati (tag fissato): `gen/db/{utils,generic,base,txn,undoredo}.py`, `plugins/db/dbapi/{sqlite,dbapi}.py`, `gen/lib/{person,family,childref,childreftype,date,surnamebase,name}.py`, `plugins/{importer/importxml,export/exportxml,lib/libgrampsxml}.py`, `gen/{const,user}.py`, `cli/user.py`, `gen/utils/resourcepath.py`, `version.py`, `COPYING`, `setup.py`.

## Browser: alternative valutate

| Soluzione | Vantaggio | Costo per questa richiesta | Decisione |
|---|---|---|---|
| GTK in container + noVNC | Intero desktop Gramps subito disponibile | UI desktop, sottomenù, sessione grafica/desktop remoto; touch e impaginazione personalizzata richiedono molte modifiche | Non scelta |
| Gramps Web + Web API | Ecosistema web ufficiale, Docker, account, funzioni genealogiche estese, servizi asincroni | Necessario scegliere e collaudare insieme una versione API/frontend compatibile con il core esatto 6.0.8; una nuova UI accessibile richiede comunque lavoro. I tag `latest` cambiano anche motore/API | Buona base per fase multiutente; non incorporata in questo prototipo |
| UI dedicata + core Gramps 6.0.8 | Nativa web, controllo completo del percorso semplificato, motore fissato e sorgenti inclusi, meno servizi | API applicativa limitata da realizzare e verificare; mancano molte funzioni già disponibili in Gramps Web | Scelta per il prototipo locale |

La preferenza per il web è soddisfatta: non viene trasmesso un desktop GTK. Le librerie GI/GTK installate nel container sono dipendenze del core/plugin headless; non c’è server X o VNC. Questa scelta non equivale a dimostrare la superiorità generale sul progetto Gramps Web: è una riduzione dello scope alla prima interfaccia e al vincolo della versione.

Fonti primarie consultate il 16 ottobre 2026:

- [Gramps tag v6.0.8](https://github.com/gramps-project/gramps/tree/v6.0.8)
- [Gramps COPYING](https://github.com/gramps-project/gramps/blob/v6.0.8/COPYING)
- [Gramps Web: deploy Docker](https://www.grampsweb.org/install_setup/deployment/)
- [Gramps Web: configurazione](https://www.grampsweb.org/install_setup/configuration/)
- [Gramps Web: aggiornamenti e significato di latest](https://www.grampsweb.org/install_setup/update/)

## Percorso di una modifica

Browser statico → JSON autenticato + CSRF + revisione → Service → Engine → oggetti/DbTxn Gramps → backend SQLite ufficiale. Un unico processo/thread possiede la connessione, serializza modifiche e backup. Nessuna connessione SQLite creata dall’applicazione per query proprie.

Le persone sono identificate dagli handle nativi, i numeri leggibili sono Gramps ID. Le famiglie mantengono riferimenti reciproci nei genitori e nei figli; ChildRef conserva due tipi di filiazione, distinti per ruolo genitore. Nuove persone possono avere sesso sconosciuto e nuovi legami sono sconosciuti per default. I ruoli vengono scelti esplicitamente e non vengono inferiti da trascinamenti, distanza o genere.

`workspace.json` conserva coordinate, blocchi e revisione. Il riordino usa ordinamento topologico e posizionamento vicino ai genitori, con ostacoli rettangolari. Le posizioni bloccate sono vincoli duri. La disposizione usa ogni handle una sola volta, preservando antenati condivisi. Lo spostamento di ramo visita i discendenti con insieme di handle e rifiuta collisioni esterne. Il layout non è un algoritmo professionale di minimizzazione degli attraversamenti; vedere i limiti.

La history combina native undo/redo per transazioni genealogiche e snapshot delle posizioni per azioni visive, in memoria fino a 50 operazioni. L’importazione è una sostituzione del solo archivio vuoto tramite staging, non una sequenza di modifiche nel database corrente. Il rollback dopo errore del processo durante il cambio directory non è un journal distribuito: sono mantenuti i precedenti archivi vuoti per recupero.

La composizione usa coordinate logiche trasversali/progressive, trasformate in x/y secondo la direzione verticale/orizzontale; le schede restano leggibili, senza ruotare il testo. I fratelli sono raccolti per insieme di genitori e generazione, avvolti in fasce di capacità scelta e sfalsati. L’inizio della generazione successiva dipende dalla profondità massima delle fasce precedenti. I blocchi manuali restano vincoli finché viene scelta esplicitamente la ricomposizione completa. La history conserva anche direzione/capacità/sfalsatura.

La funzione `connections` è condivisa da canvas e stampa: steli dei genitori, raccordo famiglia con ID e steli dei figli; curve quadratiche arrotondano i percorsi. Una corsia esterna raggiunge le fasce successive senza attraversare i fratelli già disposti, nei layout regolari. Colore derivato stabilmente dall’ID, palette di otto tinte; aloni chiari separano visivamente gli incroci. La selezione evidenzia famiglie e persone relative senza cambiare il grafo; il pannello espone i tipi reali di ChildRef per distinguere i casi misti che un singolo connettore familiare sintetizza. Non si tratta di un risolutore completo di instradamento con ostacoli per tutti gli alberi o le posizioni manuali.

`Workspace` gestisce il catalogo degli alberi e un servizio separato per ciascun archivio caricato, tutti nello stesso thread proprietario. Ogni nuovo albero riceve un ID UUID e directory distinte per database, layout, media e backup; l’archivio originale resta nei percorsi precedenti. La sottocartella riservata dei media dei nuovi alberi è esclusa dai backup del primo. Cambiare albero conserva le connessioni/history degli altri finché il processo resta aperto. Le richieste di modifica portano sia ID albero sia revisione: una vecchia scheda non può scrivere accidentalmente nell’archivio appena aperto altrove.

La cancellazione di una persona richiede conferma esplicita e, in modalità reale, un backup completato. Usa `DbTxn` e `delete_person_from_database` di Gramps 6.0.8, che pulisce ruoli nelle famiglie, riferimenti ai figli e backlink/associazioni. Non si implementa una cancellazione a cascata di parenti, fonti, eventi o media. La stessa history nativa consente il recupero. Non è prevista la cancellazione di un intero albero.

## Stampa

Una sola funzione calcola rettangolo di ingombro, foglio in mm, inset margine+sicurezza, traslazione centrata e scala. La stessa funzione genera l’SVG usato nell’anteprima e nel download. CairoSVG converte quell’SVG in PDF: nessun secondo layout, screenshot raster o CSS print dipendente dal browser. Test con lettore PDF sulla MediaBox fisica; prova visiva separata sul file generato. Il font nel container è DejaVu Sans. L’SVG scaricato cita il font ma non lo incorpora: su un sistema privo di DejaVu il visualizzatore può sostituirlo; per stampa fedele usare il PDF con font inclusi da Cairo.

## Dati e recupero

Le copie di sicurezza sono prodotte con l’export ufficiale nello stesso thread del servizio. Il media volume è letto senza seguire link esterni. ZIP con manifest hash, XML, file UI e cartella media; nessun secret. Il ripristino si esegue offline in volumi vuoti e passa sempre dall’importatore Gramps. Non si copiano file di database attivi e non si riscrivono le tabelle.

## Licenza

I file upstream dichiarano GPL versione 2 o successiva. I sorgenti nuovi e l’insieme vengono consegnati con la stessa scelta GPL-2.0-or-later e senza garanzia, con testo della licenza e sorgenti originali completi inclusi. Nessun file upstream modificato, nessun codice Gramps Web incorporato. Per una futura distribuzione binaria mantenere gli avvisi e fornire il sorgente corrispondente completo anche dei componenti per cui è richiesto; i pacchetti Debian mantengono le proprie licenze. Questo è un riepilogo operativo della licenza del progetto, non una valutazione legale personalizzata.
