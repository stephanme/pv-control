import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { PvControl, PvControlService } from './pv-control.service';

describe('ChargeControlServiceService', () => {
  let httpMock: HttpTestingController;
  let service: PvControlService;

  let pvControlData: PvControl;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [
        HttpClientTestingModule
      ]
    });
    service = TestBed.inject(PvControlService);
    httpMock = TestBed.inject(HttpTestingController);

    pvControlData = {
      meter: {
        power_pv: 5000,
        power_consumption: 3000,
        power_grid: 2000
      },
      charger: {
        phases: 3,
        power_car: 2000,
        max_current: 8
      }
    };
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should getPvControl()', () => {
    service.getPvControl().subscribe(data => {
      expect(data).toEqual(pvControlData);
    });
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);
  });

  it('should putPvControlPhases()', () => {
    service.putPvControlPhases(1).subscribe();

    const req = httpMock.expectOne('./api/pvcontrol/charger/phases');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toBe(1);
    req.flush(null);
  });
});
