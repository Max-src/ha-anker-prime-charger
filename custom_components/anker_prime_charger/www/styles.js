/**
 * Styles every card shares. --anker-port-active-color: the colour of a port
 * in use (the Anker app's); a theme or card-mod can change it.
 */
import { css } from "./lib/lit-all.js";

export const sharedStyles = css`
  :host {
    display: block;
    --anker-port-active-color: #00cbeb;
  }
  .offline {
    opacity: 0.5;
    filter: grayscale(1);
  }
`;
