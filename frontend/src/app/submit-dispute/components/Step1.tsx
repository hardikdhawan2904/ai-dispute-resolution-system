"use client";

import { useState } from "react";
import { UseFormReturn } from "react-hook-form";
import { Loader2, CheckCircle2, XCircle } from "lucide-react";
import { FormValues } from "../schema";
import { FInput, SectionCard, InfoBanner } from "./FormControls";
import { lookupCustomer } from "@/lib/api";

interface Step1Props {
  form: UseFormReturn<FormValues>;
}

export default function Step1({ form }: Step1Props) {
  const { register, formState: { errors }, setValue, watch } = form;

  const [lookupState, setLookupState] = useState<"idle" | "loading" | "found" | "not_found">("idle");

  const customerId = watch("customer_id");

  async function handleCustomerIdBlur() {
    const id = customerId?.trim();
    if (!id) return;

    setLookupState("loading");
    const customer = await lookupCustomer(id);

    if (customer) {
      setValue("customer_name", customer.full_name, { shouldValidate: true });
      setValue("email", customer.email, { shouldValidate: true });
      setValue("phone", customer.phone, { shouldValidate: true });
      setLookupState("found");
    } else {
      setValue("customer_name", "");
      setValue("email", "");
      setValue("phone", "");
      setLookupState("not_found");
    }
  }

  return (
    <div className="space-y-4">
      <SectionCard
        title="Customer Details"
        subtitle="Enter your Customer ID to load your registered account information"
      >
        <div className="space-y-4">
          {/* Customer ID with lookup */}
          <div>
            <div className="relative">
              <FInput
                label="Customer ID"
                required
                placeholder="CUST-00001"
                error={errors.customer_id?.message}
                {...register("customer_id")}
                onBlur={handleCustomerIdBlur}
              />
              {lookupState === "loading" && (
                <div className="absolute right-3 top-8 flex items-center gap-1.5 text-xs text-gray-400">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  Looking up…
                </div>
              )}
              {lookupState === "found" && (
                <div className="absolute right-3 top-8 flex items-center gap-1.5 text-xs text-green-500">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  Customer found
                </div>
              )}
              {lookupState === "not_found" && (
                <div className="absolute right-3 top-8 flex items-center gap-1.5 text-xs text-red-500">
                  <XCircle className="w-3.5 h-3.5" />
                  Customer not found — please check your Customer ID
                </div>
              )}
            </div>
          </div>

          {/* Always read-only — populated from DB via lookup, never user-editable */}
          <FInput
            label="Full Name"
            required
            placeholder="Loaded from your bank record"
            error={errors.customer_name?.message}
            readOnly
            className="bg-gray-50 cursor-not-allowed"
            {...register("customer_name")}
          />

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <FInput
              label="Email Address"
              required
              type="email"
              placeholder="Loaded from your bank record"
              error={errors.email?.message}
              readOnly
              className="bg-gray-50 cursor-not-allowed"
              {...register("email")}
            />
            <FInput
              label="Phone Number"
              required
              type="tel"
              placeholder="Loaded from your bank record"
              error={errors.phone?.message}
              readOnly
              className="bg-gray-50 cursor-not-allowed"
              {...register("phone")}
            />
          </div>
        </div>

        <div className="mt-4">
          <InfoBanner>
            Enter your Customer ID to automatically load your registered details.
            Your information is used only for dispute processing and is not shared with third parties.
          </InfoBanner>
        </div>
      </SectionCard>
    </div>
  );
}
