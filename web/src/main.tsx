import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { AppRoutes } from "./AppRoutes";
import "./theme.css";

const queryClient = new QueryClient();
const container = document.getElementById("root");
if (!container) throw new Error("missing #root");

createRoot(container).render(
  <BrowserRouter>
    <QueryClientProvider client={queryClient}>
      <AppRoutes />
    </QueryClientProvider>
  </BrowserRouter>,
);
