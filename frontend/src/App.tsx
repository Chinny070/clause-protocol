import { HashRouter, Route, Routes } from "react-router-dom";
import { ClauseProvider, TxProvider, WalletProvider } from "./app/context";
import { ClaimPage } from "./pages/ClaimPage";
import { Explore } from "./pages/Explore";
import { FileClaimPage, Holder } from "./pages/HolderPages";
import { Home } from "./pages/Home";
import { Limits, NotFound } from "./pages/Limits";
import { IssuePage, Manufacturer, ProgramPage, TermsPage } from "./pages/ManufacturerPages";
import { PassportPage } from "./pages/PassportPage";
import { ReceiptPage } from "./pages/ReceiptPage";
import { Layout } from "./ui/shell";

/** Routes are hash-based so every page (including a shareable Resolution Receipt) works on any static host. */
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="explore" element={<Explore />} />
        <Route path="passport/:id" element={<PassportPage />} />
        <Route path="passport/:id/claim" element={<FileClaimPage />} />
        <Route path="claim/:id" element={<ClaimPage />} />
        <Route path="receipt/:id" element={<ReceiptPage />} />
        <Route path="holder" element={<Holder />} />
        <Route path="manufacturer" element={<Manufacturer />} />
        <Route path="manufacturer/program/:id" element={<ProgramPage />} />
        <Route path="manufacturer/program/:id/terms/new" element={<TermsPage />} />
        <Route path="manufacturer/program/:id/issue" element={<IssuePage />} />
        <Route path="program/:id" element={<ProgramPage />} />
        <Route path="limits" element={<Limits />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

export function App() {
  return (
    <ClauseProvider>
      <WalletProvider>
        <TxProvider>
          <HashRouter>
            <AppRoutes />
          </HashRouter>
        </TxProvider>
      </WalletProvider>
    </ClauseProvider>
  );
}
