# OpenBody standards composition

OpenBody is intentionally a coordination/model protocol, not a replacement for mature domain standards.

## HL7 FHIR

Use FHIR for clinical/EHR information exchange, including observations, medications, conditions, procedures, care plans, provenance, and other clinical resources. OpenBody references FHIR evidence and uses it to calibrate or explain computational state; it does not redefine those resources.

## DICOM / DICOMweb

Use DICOM for medical imaging and DICOMweb for web-based imaging exchange. OpenBody references imaging studies/instances and model-derived features through evidence references and provenance.

## IEEE 11073

Use applicable IEEE 11073 device specializations for interoperable personal health device communication. This includes current standards for basic wearable ECG and continuous glucose monitors. OpenBody consumes the resulting observations and device provenance rather than defining a new device wire protocol.

## GA4GH

Use GA4GH standards for genomic data representation, genomic knowledge, discovery, authorization, and federated analysis where applicable. OpenBody's genomic coordinates and state assertions should reference canonical GA4GH objects rather than invent competing variant representations.

## Authorization

OpenBody keeps authority external. OAuth/OIDC, capability systems, Mandamus, or future authorization mechanisms may provide the grant referenced by `AuthorityReference`. Installation/discovery of a model is never itself a grant.

## Principle

```text
FHIR / DICOM / IEEE 11073 / GA4GH / other domain standards
                         |
                         v
                  EvidenceReference
                         |
                         v
                      OpenBody
       state / models / simulation / calibration
```

OpenBody standardizes what the evidence *means to an executable biological model*, which model produced the claim, how uncertain it is, what counterfactual was executed, and what happened afterward.
