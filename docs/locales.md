
# 📘 Documentație: Corelarea mesajelor WebSocket cu fișierul `locales`

## (Integrare custom în Home Assistant)

---

## 1. Scop

Această documentație descrie mecanismul prin care aplicația oficială:

* primește **evenimente prin WebSocket**
* le corelează cu **definiții interne de stare**
* și le afișează ca **mesaje localizate (traduse)** folosind fișierul `locales`

Scopul este reproducerea fidelă a acestui comportament într-o integrare Home Assistant.

---

## 2. Arhitectură generală

Fluxul complet este:

```text
WebSocket (backend)
        ↓
states.active (payload realtime)
        ↓
mapare pe baseStates (definiții interne)
        ↓
UI logic (alerts / notify)
        ↓
locales (traduceri i18n)
        ↓
mesaj final afișat
```

---

## 3. Structura datelor WebSocket

Backend-ul trimite stările active sub forma:

```json
{
  "states": {
    "active": {
      "105": {
        "active": true,
        "name": "FILTER_INTERVAL"
      }
    }
  }
}
```

### Semnificație:

| Câmp     | Rol                           |
| -------- | ----------------------------- |
| `105`    | ID unic al stării             |
| `active` | dacă starea este activă       |
| `name`   | **cheie semantică** (NU text) |

👉 `name` este cheia centrală în tot mecanismul.

---

## 4. Definițiile interne (`baseStates`)

Aplicația nu folosește direct payload-ul WebSocket pentru afișare.
Există un layer intermediar: **baseStates**.

Exemplu:

```json
{
  "id": 105,
  "purpose": "notify",
  "severity": 3,
  "type": "FILTER_INTERVAL"
}
```

### Roluri:

| Câmp       | Descriere                               |
| ---------- | --------------------------------------- |
| `id`       | ID numeric                              |
| `purpose`  | tip UI (`notify`, `alarm`, etc.)        |
| `severity` | severitate                              |
| `type`     | cheia de traducere (identică cu `name`) |

---

## 5. Corelarea WebSocket → baseStates

În frontend există logică echivalentă cu:

```js
if (payload.states.active) {
  Object.values(payload.states.active).forEach(item => {
    const baseState = getBaseState(item.name);
    if (baseState) alerts.push(baseState);
  });
}
```

### Interpretare:

* `item.name` → `"FILTER_INTERVAL"`
* se face lookup în `baseStates`
* rezultatul este un obiect complet cu metadate

---

## 6. Fișierul `locales`

Fișierul:

```text
locales.js
```

conține traducerile:

```js
states: {
  FILTER_INTERVAL: "Filter replacement interval"
}
```

### Observații:

* cheia este aceeași cu `type` din `baseStates`
* valorile sunt texte localizate
* fișierul este generat (bundle), nu sursa originală

---

## 7. Generarea mesajului final

UI construiește mesajul astfel:

```js
"S " + state.id + " - " + t("states." + state.type)
```

Exemplu concret:

```text
S 105 - Filter replacement interval
```

### Componente:

| Element | Sursă                            |
| ------- | -------------------------------- |
| `S`     | prefix logic (non-alarm)         |
| `105`   | `baseState.id`                   |
| text    | `locales.states.FILTER_INTERVAL` |

---

## 8. Tipuri de prefix (observat)

| Prefix | Semnificație    |
| ------ | --------------- |
| `S`    | status / notify |
| `E`    | error / alarm   |

Determinarea prefixului se face pe baza:

* `purpose`
* sau alt flag intern (alarm vs notify)

---

## 9. Rolul real al `locales`

⚠️ Important:

`locales` NU conține logică.
Este doar un **dicționar de traduceri**.

### Responsabilități:

* transformă chei semantice → text afișabil
* permite multi-language
* separă UI de backend

---

## 10. Concluzie arhitecturală

`FILTER_INTERVAL` este:

* ❌ NU text final
* ❌ NU mesaj complet
* ✅ **cod semantic de stare**

Acesta este:

```text
WebSocket → name
        ↓
baseStates → type
        ↓
locales → text final
```

---

## 11. Implementare în Home Assistant

### 11.1 Model recomandat

În integrarea ta:

```python
class DeviceState:
    id: int
    code: str          # FILTER_INTERVAL
    purpose: str       # notify / alarm
    severity: int
```

---

### 11.2 Dicționar de traduceri

```python
LOCALIZATION = {
    "FILTER_INTERVAL": "Filter replacement interval"
}
```

(opțional: multi-language ulterior)

---

### 11.3 Procesare WebSocket

```python
def process_states(payload):
    active = payload.get("states", {}).get("active", {})
    alerts = []

    for state_id, data in active.items():
        code = data["name"]

        base = BASE_STATES.get(code)
        if not base:
            continue

        message = build_message(base)
        alerts.append(message)

    return alerts
```

---

### 11.4 Generare mesaj

```python
def build_message(base):
    prefix = "E" if base["purpose"] == "alarm" else "S"
    text = LOCALIZATION.get(base["type"], base["type"])

    return f"{prefix} {base['id']} - {text}"
```

---

### 11.5 Integrare în Home Assistant

Recomandări:

* expune fiecare alert ca:

  * `sensor`
  * sau `binary_sensor`
* sau agregat:

  * `sensor.device_notifications`

Exemplu:

```yaml
sensor:
  - name: "Device Alerts"
    state: "{{ states('sensor.device_alerts_raw') }}"
```

---

## 12. Observații importante

### 12.1 Backend-ul este “agnostic de UI”

* nu trimite texte
* trimite doar coduri

👉 frontend-ul controlează complet afișarea

---

### 12.2 Sistem extensibil

Poți adăuga:

* alte limbi
* mapping custom
* override texte

---

### 12.3 Robustness

Dacă nu există traducere:

```python
text = LOCALIZATION.get(code, code)
```

---

## 13. TL;DR

* WebSocket trimite: `"FILTER_INTERVAL"`
* Frontend mapează la `baseStates`
* UI construiește mesaj:

  ```text
  S 105 - <traducere>
  ```
* `locales` doar traduce cheia

---

## 14. Recomandare finală

Pentru integrarea ta:

👉 implementează exact acest pipeline:

```text
WebSocket → code → baseState → translation → formatted message
```

NU încerca să folosești direct text din backend — nu există.

