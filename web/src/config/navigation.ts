import {
  FileText,
  Settings,
  Shield,
  TerminalSquare,
  Calculator
} from "lucide-react";

export const navItems = [
  { label: "Advisory", icon: TerminalSquare, path: "/" },
  { label: "Clients", icon: Shield, path: "/clients" },
  { label: "Valuation", icon: Calculator, path: "/valuation" },
  { label: "Reports", icon: FileText, path: "/reports" },
  { label: "System", icon: Settings, path: "/system" }
];
