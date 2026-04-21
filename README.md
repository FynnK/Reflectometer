---
tags:
  - electronics
  - hardware-design
  - water-sensor
  - obsidian-skills
status: design-complete
---

---
tags:
  - electronics
  - hardware-design
  - water-sensor
status: design-complete
---

# Multi-LED Spectral Water Quality Sensor

> [!info] Project Overview
> A 24-bit isolated sensing system using pulsed 100mA current sources to measure liquid reflection across three wavelengths (Red, Green, Blue).

## System Architecture

```mermaid
graph TD
    %% -- Non-Isolated Side --
    subgraph NonIsolated ["Power and Control (Digital)"]
        USB[MicroUSB Connector]
        ESP32[ESP32-C3 MCU]
        C_IN[10uF CL21A106]
    end

    %% -- Isolation Barrier --
    subgraph Moat ["Isolation Barrier"]
        ISO1[ISO6742 SPI]
        ISO2[ISO6742 Control]
        ISO3[ISO6742 Extra]
        TRACO[TEA 1-0505 DC/DC]
    end

    %% -- Isolated Side --
    subgraph Isolated ["Isolated Analog Island"]
        %% Power Path
        L47[47uH WE Inductor]
        C_BULK[10uF Filtered]
        TPS[TPS60403 Inverter]
        
        %% Control Signals
        PWM[PWM Filter]
        GATE_SEL[BS170 Selector Gates]
        
        %% Signal Chain
        PD[BPW34S Photodiode]
        TIA[TLV172 TIA]
        ADC[ADS131M02]
        
        %% LED Current Path
        LEDS[RGB LED Array]
        SINK[BS170 Regulator]
        RSENSE[10 ohm Sense Resistor]
    end

    %% Cross-Barrier Links
    USB --> C_IN
    C_IN --> ESP32
    C_IN --> TRACO
    ESP32 --> ISO1
    ESP32 --> ISO2
    
    %% Isolated Routing
    TRACO --> L47
    L47 --> C_BULK
    C_BULK --> TPS
    C_BULK --> LEDS
    
    ISO1 --> ADC
    ISO2 --> PWM
    ISO2 --> GATE_SEL
    
    LEDS --> GATE_SEL
    GATE_SEL --> SINK
    SINK --> RSENSE
    RSENSE --> ADC
    
    PD --> TIA
    TIA --> ADC
````

## Hardware Component Logic

### 1. Power & Noise Suppression

- **Isolated DC/DC:** Uses the [[TEA 1-0505]] to break ground loops.
    
- **The Filter:** A Pi-filter using the **47uH Würth Inductor** and **Ferrite Beads** to scrub switching noise.
    
- **Negative Rail:** The **TPS60403** provides a -5V rail for the **TLV172** to allow the TIA to swing to absolute zero.
    

### 2. The 100mA Pulsed Source

> [!tip] Ratiometric Measurement
> 
> By routing the voltage from the **10 ohm Sense Resistor** back to ADC Channel 2, we calculate the ratio of reflected light to actual LED current. This cancels out power supply ripples.

- **Regulation:** TLV172 + BS170 (Main Sink).
    
- **Switching:** 3x BS170 (Color Selectors).
    

## Component List & Budget

|**Component**|**Function**|**Cost**|
|---|---|---|
|[[ADS131M02]]|24-bit ADC|€4.41|
|[[ISO6742]] (x3)|Digital Isolation|€7.68|
|[[TLV172]] (x2)|TIA & Current Source|€2.96|
|[[TEA 1-0505]]|Isolated Power|€1.65|

**Total Estimated BOM:** €24.64 ^total-cost