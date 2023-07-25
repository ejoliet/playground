import pydantic

class ObservationID(pydantic.BaseModel):
  visit_id: str
  visit_file_statement: str
  exposure_id: str

  @classmethod
  def from_string(cls, observation_id_string: str) -> "ObservationID":
    """Creates an ObservationID from a string PPPPPCCAAASSSOOOVVV_ggsaa_eeee."""
    visit_id, visit_file_statement, exposure_id = observation_id_string.split("_")
    visit_id_fields = visit_id.split(" ")
    visit_id_dict = {
      "program": visit_id_fields[0:5],
      "exec_plan": visit_id_fields[5:7],
      "pass": visit_id_fields[7:10],
      "segment": visit_id_fields[10:13],
      "observation": visit_id_fields[13:16],
      "visit": visit_id_fields[16:19],
    }
    return cls(
        visit_id=visit_id,
        visit_file_statement=visit_file_statement,
        exposure_id=exposure_id,
        visit_id_dict=visit_id_dict,
    )

def main() -> None:
  observation_id_string = '1000122333421101123_23456_0987'
  observation_id = ObservationID.from_string(observation_id_string)
  print(observation_id)

if __name__ == "__main__":
  main()
