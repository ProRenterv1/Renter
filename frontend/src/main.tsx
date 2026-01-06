import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";
import { Elements } from "@stripe/react-stripe-js";
import { loadStripe } from "@stripe/stripe-js";
import { GoogleIdentityProvider } from "./lib/google-identity";

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("Root element not found");
}

const isOpsBuild = import.meta.env.VITE_OPS_BUILD === "1";
const stripePublishableKey = import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY;
const stripePromise = stripePublishableKey ? loadStripe(stripePublishableKey) : null;

if (!isOpsBuild && !stripePublishableKey) {
  throw new Error("Missing Stripe publishable key (VITE_STRIPE_PUBLISHABLE_KEY).");
}

const app = (
  <GoogleIdentityProvider>
    <BrowserRouter>
      <App opsBuild={isOpsBuild} />
    </BrowserRouter>
  </GoogleIdentityProvider>
);

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <Elements stripe={stripePromise}>
      {app}
    </Elements>
  </React.StrictMode>
);
