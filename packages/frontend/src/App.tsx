import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import DatasetStudio from "./pages/DatasetStudio";
import VoicePlayground from "./pages/VoicePlayground";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Navigate to="/playground" replace />} />
        <Route path="/dataset" element={<DatasetStudio />} />
        <Route path="/playground" element={<VoicePlayground />} />
      </Route>
    </Routes>
  );
}
