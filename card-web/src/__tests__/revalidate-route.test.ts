import { beforeEach, describe, expect, it, vi } from "vitest";

const revalidatePath = vi.fn();
const revalidateTag = vi.fn();

vi.mock("next/cache", () => ({
  revalidatePath,
  revalidateTag,
}));

describe("POST /api/revalidate", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    process.env.REVALIDATION_SECRET = "secret";
  });

  it("invalidates the username cache tag as well as the profile path", async () => {
    const { POST } = await import("@/app/api/revalidate/route");

    const request = new Request("https://nxme.ai/api/revalidate", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-revalidation-secret": "secret",
      },
      body: JSON.stringify({ username: "janedoe" }),
    });

    const response = await POST(request as never);
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.revalidated).toBe(true);
    expect(revalidateTag).toHaveBeenCalledWith("card:janedoe");
    expect(revalidatePath).toHaveBeenCalledWith("/janedoe");
  });
});
