import gsap from "gsap";

const MAX_SPARKS = 12;

export function celebrateGold(layer: HTMLElement, enabled: boolean): void {
  layer.replaceChildren();
  if (!enabled) {
    return;
  }
  for (let i = 0; i < MAX_SPARKS; i += 1) {
    const spark = document.createElement("div");
    spark.className = "spark";
    spark.style.left = `${20 + Math.random() * 60}%`;
    spark.style.top = `${18 + Math.random() * 20}%`;
    layer.append(spark);
    gsap.fromTo(
      spark,
      { opacity: 0, y: 12, scale: 0.4 },
      {
        opacity: 0.8,
        y: -24 - Math.random() * 30,
        scale: 1,
        duration: 0.8 + Math.random() * 0.4,
        delay: Math.random() * 0.2,
        yoyo: true,
        repeat: 1,
      },
    );
  }
}

export function clearCelebration(layer: HTMLElement): void {
  gsap.killTweensOf(layer.querySelectorAll(".spark"));
  layer.replaceChildren();
}
