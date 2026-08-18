import { NextResponse } from "next/server";
import { getDeliveryPlans } from "@/lib/db";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  return NextResponse.json({ delivery_plans: getDeliveryPlans() });
}
