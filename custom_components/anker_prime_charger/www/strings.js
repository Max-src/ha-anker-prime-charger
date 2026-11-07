/**
 * The cards' words, in the user's language (Home Assistant's profile
 * setting), English when there is no translation. `{name}` in a string is
 * replaced by the value of the same name.
 *
 * The card picker's names and descriptions stay in English: they are listed
 * before any card knows the user's language.
 */

const STRINGS = {
  en: {
    "editor.device": "Charger",
    "port.history": "{port}: power history",
    // the 3D card
    "3d.drag_to_rotate": "Rotate by dragging",
    "3d.drag_to_rotate.helper":
      "Turn the charger by dragging it (or with the arrow keys), zoom with Ctrl + the mouse wheel, a pinch, or + and -; its view is remembered.",
    "3d.show_cables": "Show plugged-in cables",
    "3d.show_cables.helper": "A cable in each port with a device; off, those ports are only lit.",
    "3d.show_port_power": "Show each port's power",
    "3d.show_port_power.helper": "Above each port with a device, whatever the screen shows.",
    "3d.show_controls": "Show zoom and turn buttons",
    "3d.show_controls.helper": "Buttons in the corner to zoom out and in and turn it left and right.",
    "3d.port_history": "Tap a port for its history",
    "3d.port_history.helper":
      "Tapping a port, its power or its cable opens the port's power history, as on the outputs card.",
    "3d.screen": "The screen shows",
    "3d.screen.helper":
      "Auto: what the charger shows (estimated). Power: the total output. Clock: the selected clock theme, with the time.",
    "3d.screen.auto": "Auto",
    "3d.screen.power": "Power",
    "3d.screen.clock": "Clock",
    "3d.screen.off": "Off",
    "3d.view": "3D view",
    "3d.label": "{name}: drag or use the arrow keys to turn it, + and - to zoom",
    "3d.zoom_out": "Zoom out",
    "3d.zoom_in": "Zoom in",
    "3d.turn_left": "Turn left",
    "3d.turn_right": "Turn right",
    "3d.knob": "Pressing the knob",
    "3d.knob.helper": "Wake: the charger's screen wakes on its power page, as when you press its knob.",
    "3d.knob.wake": "Wakes the screen",
    "3d.knob.none": "Does nothing",
    "3d.arrows": "Arrows beside the screen",
    "3d.arrows.helper": "Brightness: two arrows on the screen's glass dim and brighten the charger's screen (5 % a tap).",
    "3d.arrows.none": "None",
    "3d.arrows.brightness": "Brightness",
    "3d.wake": "Knob: wake the screen",
    "3d.dimmer": "Screen brightness down",
    "3d.brighter": "Screen brightness up",
    "3d.brightness": "{value} %",
    // the outputs card
    "outputs.usb_c": "USB-C Output",
    "outputs.usb_a": "USB-A Output",
    "outputs.show_details": "Show voltage and current",
    "outputs.show_switches": "Show on/off buttons",
    "outputs.show_switches.helper":
      "A button next to each port. A1 and A2 share theirs: the charger turns both USB-A ports on or off together.",
    "outputs.port_history": "Tap a port for its history",
    "outputs.port_history.helper":
      "Tapping a port opens its power history; the port under the mouse is highlighted.",
    "outputs.switch": "{ports} on/off",
    "outputs.turn_on": "Turn {ports} on",
    "outputs.turn_off": "Turn {ports} off",
    "outputs.unknown": "{ports}: unknown",
  },
  fr: {
    "editor.device": "Chargeur",
    "port.history": "{port} : historique de la puissance",
    "3d.drag_to_rotate": "Tourner en le faisant glisser",
    "3d.drag_to_rotate.helper":
      "Tourner le chargeur en le faisant glisser (ou avec les flèches), zoomer avec Ctrl + la molette, en pinçant, ou avec + et - ; la vue est mémorisée.",
    "3d.show_cables": "Afficher les câbles branchés",
    "3d.show_cables.helper": "Un câble dans chaque port avec un appareil ; sinon, ces ports sont seulement allumés.",
    "3d.show_port_power": "Afficher la puissance de chaque port",
    "3d.show_port_power.helper": "Au-dessus de chaque port avec un appareil, quel que soit l'écran affiché.",
    "3d.show_controls": "Afficher les boutons de zoom et de rotation",
    "3d.show_controls.helper": "Des boutons dans le coin pour zoomer, dézoomer et le tourner à gauche et à droite.",
    "3d.port_history": "Toucher un port pour son historique",
    "3d.port_history.helper":
      "Toucher un port, sa puissance ou son câble ouvre l'historique de puissance du port, comme sur la carte des sorties.",
    "3d.screen": "L'écran affiche",
    "3d.screen.helper":
      "Auto : ce qu'affiche le chargeur (estimé). Puissance : la puissance totale. Horloge : le thème d'horloge choisi, avec l'heure.",
    "3d.screen.auto": "Auto",
    "3d.screen.power": "Puissance",
    "3d.screen.clock": "Horloge",
    "3d.screen.off": "Éteint",
    "3d.view": "Vue 3D",
    "3d.label": "{name} : faites glisser ou utilisez les flèches pour le tourner, + et - pour zoomer",
    "3d.zoom_out": "Dézoomer",
    "3d.zoom_in": "Zoomer",
    "3d.turn_left": "Tourner à gauche",
    "3d.turn_right": "Tourner à droite",
    "3d.knob": "Appuyer sur la molette",
    "3d.knob.helper": "Réveiller : l'écran du chargeur se rallume sur sa page de puissance, comme quand on appuie sur sa molette.",
    "3d.knob.wake": "Réveille l'écran",
    "3d.knob.none": "Ne fait rien",
    "3d.arrows": "Flèches à côté de l'écran",
    "3d.arrows.helper": "Luminosité : deux flèches sur la vitre de l'écran baissent et montent la luminosité de l'écran du chargeur (5 % par appui).",
    "3d.arrows.none": "Aucune",
    "3d.arrows.brightness": "Luminosité",
    "3d.wake": "Molette : réveiller l'écran",
    "3d.dimmer": "Baisser la luminosité de l'écran",
    "3d.brighter": "Augmenter la luminosité de l'écran",
    "3d.brightness": "{value} %",
    "outputs.usb_c": "Sortie USB-C",
    "outputs.usb_a": "Sortie USB-A",
    "outputs.show_details": "Afficher la tension et le courant",
    "outputs.show_switches": "Afficher les boutons marche/arrêt",
    "outputs.show_switches.helper":
      "Un bouton à côté de chaque port. A1 et A2 partagent le leur : le chargeur allume ou éteint les deux ports USB-A ensemble.",
    "outputs.port_history": "Toucher un port pour son historique",
    "outputs.port_history.helper":
      "Toucher un port ouvre son historique de puissance ; le port sous la souris est mis en évidence.",
    "outputs.switch": "{ports} marche/arrêt",
    "outputs.turn_on": "Allumer {ports}",
    "outputs.turn_off": "Éteindre {ports}",
    "outputs.unknown": "{ports} : inconnu",
  },
};

/** The user's language ("fr" for "fr-CA"), if the cards have it, else "en". */
function language(hass) {
  const wanted = (hass?.locale?.language || hass?.language || "en").toLowerCase();
  if (STRINGS[wanted]) return wanted;
  const base = wanted.split("-")[0];
  return STRINGS[base] ? base : "en";
}

/** The string `key` in the user's language, with `values` filled in. */
export function t(hass, key, values = {}) {
  const text = STRINGS[language(hass)][key] ?? STRINGS.en[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (match, name) => (name in values ? String(values[name]) : match));
}
