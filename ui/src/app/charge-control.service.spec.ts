import { TestBed } from '@angular/core/testing';

import { ChargeControlService } from './charge-control.service';

describe('ChargeControlServiceService', () => {
  let service: ChargeControlService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(ChargeControlService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
