export const PROFILE_BROWSE_MODES = [
  { value: "biometric", label: "Biometric Available Profiles" },
  { value: "no_face", label: "No Biometric Profiles" },
];

export function browsePeopleCandidates(rankedPeople, allPeople, mode) {
  if (mode === "no_face") {
    return (allPeople || [])
      .filter((person) => person.lifecycle_status === "ACTIVE" && person.biometric_status === "NO_FACE")
      .sort((left, right) => left.name.localeCompare(right.name) || left.person_id.localeCompare(right.person_id));
  }
  return (rankedPeople || []).filter((person) => person.biometric_status === "ENROLLED" && person.match);
}
