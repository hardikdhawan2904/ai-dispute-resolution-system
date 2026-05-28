"use client";

import { UseFormReturn } from "react-hook-form";
import { FormValues } from "../schema";
import { FInput, SectionCard, InfoBanner } from "./FormControls";

interface Step1Props {
  form: UseFormReturn<FormValues>;
}

export default function Step1({ form }: Step1Props) {
  const { register, formState: { errors } } = form;

  return (
    <div className="space-y-4">
      <SectionCard
        title="Customer Details"
        subtitle="Your registered account information"
      >
        <div className="space-y-4">
          <FInput
            label="Full Name"
            required
            placeholder="Rahul Verma"
            error={errors.customer_name?.message}
            {...register("customer_name")}
          />

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <FInput
              label="Customer ID"
              required
              placeholder="CUST-XXXXXX"
              error={errors.customer_id?.message}
              {...register("customer_id")}
            />
            <FInput
              label="Email Address"
              required
              type="email"
              placeholder="rahul@example.com"
              error={errors.email?.message}
              {...register("email")}
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <FInput
              label="Phone Number"
              required
              type="tel"
              placeholder="+91 98765 43210"
              error={errors.phone?.message}
              {...register("phone")}
            />
          </div>
        </div>

        <div className="mt-4">
          <InfoBanner>
            Your personal details are submitted securely and used only for dispute processing.
            We do not share your information with third parties.
          </InfoBanner>
        </div>
      </SectionCard>
    </div>
  );
}
