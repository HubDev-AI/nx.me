import { formatPrice } from "./format-price";

describe("formatPrice", () => {
  it("formats USD cents to dollar string", () => {
    expect(formatPrice(499, "usd")).toBe("$4.99");
  });

  it("formats whole-dollar amount", () => {
    expect(formatPrice(2500, "usd")).toBe("$25.00");
  });

  it("accepts uppercase currency code", () => {
    expect(formatPrice(499, "USD")).toBe("$4.99");
  });

  it("formats EUR with the en-US locale (currency symbol prefixed)", () => {
    // Intl normalizes EUR to "€" in en-US.
    expect(formatPrice(199, "eur")).toBe("€1.99");
  });

  it("formats GBP", () => {
    expect(formatPrice(999, "gbp")).toBe("£9.99");
  });

  it("formats zero", () => {
    expect(formatPrice(0, "usd")).toBe("$0.00");
  });
});
