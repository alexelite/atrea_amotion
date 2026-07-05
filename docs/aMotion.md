# Specificații Tehnice: Parametri de Control Climatizare (Încălzire / Răcire)

## 1. Metode de Comutare Sezonieră (HS / NHS)

Acest parametru determină modul de trecere între sezonul de încălzire (**HS** - *Heizsaison*) și sezonul fără încălzire (**NHS** - *Nicht-Heizsaison*).

* **HS**: Sezonul de încălzire este activ în permanență, până când se modifică manual valoarea.
* **NHS**: Sezonul fără încălzire este activ în permanență, până când se modifică manual valoarea.
* **T-ODA medie**: Comutarea HS/NHS se face automat în funcție de temperatura medie exterioară ($T_{ODA}$):
    * **Activare NHS (Sezon fără încălzire)**: $T_{ODA\text{ medie}} > \text{Prag comutare temp.} + 0.5^\circ\text{C}$
    * **Activare HS (Sezon de încălzire)**: $T_{ODA\text{ medie}} < \text{Prag comutare temp.} - 0.5^\circ\text{C}$
* **T-ODA medie + surplus**: Comutarea se face automat în funcție de temperatura medie $T_{ODA}$, dar permite menținerea modului NHS (fără încălzire) chiar și atunci când $T_{ODA}$ este mai scăzută, dacă interiorul este cald:
    * **Activare NHS**: $T_{ODA\text{ medie}} > \text{Prag comutare temp.} + 0.5^\circ\text{C}$
    * **Menținere NHS (Activ în continuare)**: $T_{ODA\text{ medie}} > 0^\circ\text{C}$ **și** $T_{IDA} > \text{Temperatura solicitată} + 5^\circ\text{C}$
    * **Activare HS**: $T_{ODA\text{ medie}} < \text{Prag comutare temp.} - 0.5^\circ\text{C}$ **și** $T_{IDA} < \text{Temperatura solicitată} + 5^\circ\text{C}$

### Parametri auxiliari T-ODA (Aer Exterior)
| Parametru | Descriere |
| :--- | :--- |
| **HS/NHS comutator T-ODA** | Valoarea temperaturii medii a aerului exterior, care este utilizată ca prag pentru comutarea HS/NHS. |
| **Interval mediu T-ODA** | Lungimea intervalului de timp din care se calculează media temperaturii $T_{ODA}$. |
| **Media actuală a T-ODA** | Valoarea temperaturii medii actuale a aerului exterior. |

---

## 2. Controlul Încălzirii (Histerezis T-IDA)
*Notă: Valoarea este utilizată numai dacă încălzirea este controlată în funcție de temperatura aerului interior ($T_{IDA}$).*

* **Pornire încălzire**: Se activează atunci când:
    $$T_{IDA} < \text{Temperatura solicitată} - \text{Histerezis}$$
* **Oprire încălzire**: Se oprește atunci când:
    $$T_{IDA} > \text{Temperatura solicitată} + \text{Histerezis}$$

---

## 3. Controlul Răcirii (Histerezis și Compensare T-IDA)
*Notă: Valorile sunt utilizate numai dacă răcirea este controlată în funcție de temperatura aerului interior ($T_{IDA}$).*

### Histerezis T-IDA - răcire
* **Pornire răcire**: Se activează atunci când:
    $$T_{IDA} > \text{Temperatura solicitată} + \text{Histerezis}$$
* **Oprire răcire**: Se oprește atunci când:
    $$T_{IDA} < \text{Temperatura solicitată} - \text{Histerezis}$$

### Compensare T-IDA pentru răcire
Valoarea acestui parametru determină amânarea pornirii răcirii până la o valoare mai mare a temperaturii aerului interior (pentru economie sau confort suplimentar):
* **Activare răcire cu compensare**: Se activează doar atunci când:
    $$T_{IDA} > \text{Temperatura solicitată} + \text{Histerezis} + \text{Compensare}$$

---

> **Glosar de termeni:**
> * **$T_{ODA}$** (Outdoor Air) – Temperatura aerului exterior.
> * **$T_{IDA}$** (Indoor Air) – Temperatura aerului interior.
> * **Temperatura solicitată** – Setpoint-ul de temperatură dorit în clădire.