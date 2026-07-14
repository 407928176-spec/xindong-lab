export interface EndingDisplay {
  label: string;
  iconClassName: string;
  badgeClassName: string;
  cardClassName: string;
  panelClassName: string;
  titleClassName: string;
}

export function getEndingDisplay(result: string | null | undefined): EndingDisplay {
  if (result === "HE") {
    return {
      label: "幸福结局",
      iconClassName: "text-rose-500 bg-rose-50 ring-rose-100",
      badgeClassName: "border-rose-200 bg-rose-50 text-rose-700",
      cardClassName: "border-rose-200 bg-gradient-to-br from-white to-rose-50/70",
      panelClassName: "border-rose-100 bg-rose-50/80 ring-rose-100/70",
      titleClassName: "text-rose-700",
    };
  }

  if (result === "BE") {
    return {
      label: "遗憾结局",
      iconClassName: "text-indigo-500 bg-indigo-50 ring-indigo-100",
      badgeClassName: "border-indigo-200 bg-indigo-50 text-indigo-700",
      cardClassName: "border-indigo-200 bg-gradient-to-br from-white to-indigo-50/70",
      panelClassName: "border-indigo-100 bg-indigo-50/80 ring-indigo-100/70",
      titleClassName: "text-indigo-700",
    };
  }

  return {
    label: "普通结局",
    iconClassName: "text-amber-500 bg-amber-50 ring-amber-100",
    badgeClassName: "border-amber-200 bg-amber-50 text-amber-700",
    cardClassName: "border-amber-200 bg-gradient-to-br from-white to-amber-50/70",
    panelClassName: "border-amber-100 bg-amber-50/80 ring-amber-100/70",
    titleClassName: "text-amber-700",
  };
}
