/**
 * Registration that survives a module loaded twice (the integration's
 * resource plus a leftover manual one, say): customElements.define throws on
 * a second call, which would break the card.
 */

export function defineOnce(tag, elementClass) {
  if (!customElements.get(tag)) customElements.define(tag, elementClass);
}

/** List a card in the dashboard's card picker (once). */
export function registerCustomCard(card) {
  window.customCards = window.customCards || [];
  if (!window.customCards.some((entry) => entry.type === card.type)) {
    window.customCards.push(card);
  }
}
