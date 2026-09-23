import { Select } from "@mantine/core";
import { COUNTRY_OPTIONS, filterCountries } from "../countries.js";

export function CountrySelect({ value, onChange, required = true }) {
  return (
    <Select
      required={required}
      searchable
      label="Country"
      placeholder="Browse or search countries"
      data={value && !COUNTRY_OPTIONS.includes(value) ? [value, ...COUNTRY_OPTIONS] : COUNTRY_OPTIONS}
      value={value || null}
      onChange={(selected) => onChange(selected || "")}
      filter={filterCountries}
      nothingFoundMessage="No countries found"
    />
  );
}
